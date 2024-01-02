"""
  _____  ______ _____ _____         ____  _____   _____                     _     _             _____      _           _ _     _           
 |  __ \|  ____|_   _|  __ \       / __ \|  __ \ / ____|     /\            | |   (_)           |  __ \    | |         (_) |   | |          
 | |  | | |__    | | | |__) |_____| |  | | |__) | |         /  \   _ __ ___| |__  ___   _____  | |__) |___| |__  _   _ _| | __| | ___ _ __ 
 | |  | |  __|   | | |  _  /______| |  | |  _  /| |        / /\ \ | '__/ __| '_ \| \ \ / / _ \ |  _  // _ \ '_ \| | | | | |/ _` |/ _ \ '__|
 | |__| | |     _| |_| | \ \      | |__| | | \ \| |____   / ____ \| | | (__| | | | |\ V /  __/ | | \ \  __/ |_) | |_| | | | (_| |  __/ |   
 |_____/|_|    |_____|_|  \_\      \____/|_|  \_\______| /_/    \_\_|  \___|_| |_|_| \_/ \___| |_|  \_\___|_.__/ \__,_|_|_|\__,_|\___|_|   


Get only all collected artefacts from DFIR-Orc output 7z file and extract them by re-building their original path and extension.
The aim of this tool is to be able to run parsers which rely on file path and extension like Kape or Plaso.
The script check for each GetThis.csv file in sub directories, and extract each file listed inside.
To map a volume ID with the drive letter, the script looks for volstats.csv file.
"""

epilog_doc="""
Known limitations:
  - The file creation date reflect the script usage, as non-native python solution exists.
  - Timestomp alerts can trigger on the given files as no miliseconds/nonaseconds are used.
  - This tool fails to extract artefacts if the targeted filepath is bigger than the OS lenght limitation.
"""

import io
import os
import csv
import codecs
import typing
import tomllib
import logging
import pathlib
import datetime

from py7zr import SevenZipFile, Bad7zFile

def _naming_convention_volume_folder(volume_id, snapshot_id):
  """
  This function defines the naming convention used by this script for the root directory where artefacts are created.
  Each collected artefact belongs to a volume. If collection on volume shadow copy (vsc) is done, artefacts are collected multiple time. To distinguish each version, the root folder name includes the snaphot_id (aka vsc) if not empty.

  Excpeted results:
    - volume_id
    - volume_id (vsc {snapshot_id})

  This folder name will end up under the destination_folder given in the script parameter.
  The volume_id will be replaced later (by another function) if there is a mounted drive found in a volstats.csv file.

  Args:
    volume_id: Volume ID from a sample in GetThis.csv.
    snapshot_id: Snapshot ID from a sample in GetThis.csv.

  Returns:
    The volume folder name where the sample will be saved.
  """
  if snapshot_id == "{00000000-0000-0000-0000-000000000000}":
    return volume_id
  else:
    return f'{volume_id} (vsc {snapshot_id})'


def _parse_getthis(
  getthis_content: io.BytesIO,
  destination_folder: pathlib.Path
) -> dict:
  """
  This function returns the real path for each SampleName from the GetThis.csv file content given in parameter in a dictionnary.

  For each artefacts (aka SampleName) in GetThis.csv, the function returns the real path where to save it. It appends the root folder name, using _naming_convention_volume_folder function and changes windows path format to unix.

  Args:
    getthis_content: The GetThis.csv file content.
    destination_folder: The destination path where to save artefacts.

  Returns:
    A dictionnary where each SampleName will have its targeted file path
  """

  result = {}

  getthis = csv.DictReader(codecs.getreader('utf-8-sig')(getthis_content))

  for row in getthis:
    result[row['SampleName'].replace('\\', '/')] = {
      'path': destination_folder.joinpath(_naming_convention_volume_folder(row['VolumeID'], row['SnapshotID']), row['FullName'].replace('\\', '/')[1:]),
      'mtime': int(datetime.datetime.strptime(row['LastModificationDate'], '%Y-%m-%d %H:%M:%S.%f').timestamp()),
      'atime': int(datetime.datetime.strptime(row['LastAccessDate'], '%Y-%m-%d %H:%M:%S.%f').timestamp())
    }

  return result

def _parse_volstats(
  volstats_content: io.BytesIO
) -> dict:
  """
  This function returns the mounted drive letter for each VolumeID from the volstats.csv file content given in parameter in a dictionnary.

  Args:
    getthis_content: The volstats.csv file content.

  Returns:
    A dictionnary where each VolumeID has its mounted drive letter
  """

  result = {}

  volstats = csv.DictReader(codecs.getreader('utf-8-sig')(volstats_content))

  for row in volstats:
    # For each row if there is a MountPoint given, save it. (Keep only the letter without ':')
    if row.get('MountPoint', ''):
      result[row['VolumeID']] = row['MountPoint'][0]

  return result


def _write_file(
  file_path: pathlib.Path,
  content: io.BytesIO,
  atime: int = None,
  mtime: int = None
) -> bool:
  """
  This function write the given file content in the given file path. It creates the diretory tree if non existing. Fails if the file already exists or due any other IO errors.

  Args:
    file_path: The target file path
    content: The content of the file to write
    atime: The access time to set for the created file
    mtime: The modified time to set for the created file

  Returns:
    A boolean indicating if the file has been written.
  """

  # Write file
  try:
    # Check if already exists if yes warning
    if file_path.is_file():
      logging.warning('File %s already exists', file_path)
      return False

    # Create parent directory
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, 'wb') as file_d:
      # Write the file
      file_d.write(content.getbuffer())

  except (OSError, Exception) as err:
    logging.warning('Can\'t write file %s\n%s', file_path, err)
    return False

  # Update its m.a times if not None
  if atime and mtime:
    os.utime(file_path, times=(atime, mtime))

  return True

def _extract_artefacts_recusrive( 
  archive: typing.Union[pathlib.Path, io.BytesIO],
  destination_folder: pathlib.Path,
  log_file_with_artefacts_non_extracted: typing.TextIO,
  archive_name: str = "",
  archives_with_password: dict = {},
  report_files: list = [],
  report_destination_directory: pathlib.Path = None
) -> dict:
  """
  This function opens the 7z file given in parameter, and search for a GetThis.csv file. If found, the file is parsed. Then function iterates on each files and subfolder, if the file was listed in GetThis.csv it writes the sample using `_write_file` (see the docstring for more details).
  The function logs all files name that could not be write in `log_file_with_artefacts_non_extracted` file.
  The function is recursively called when 7z files are found.

  Args:
    archive: The archive to parse. Can be either the file path (for the first call) or the content (for the recusrive calls)
    destination_folder: The destination path where to save artefacts.
    log_file_with_artefacts_non_extracted: The file where artefacts SampleName non extracted are logged.
    archive_name: The archive name. Used for recursive called only where archive is a io.BytesIO (and doesn't contain filename).
    archives_with_password: The archives with their password if any.

  Returns:
    A dictionnary with metadata including volstats.csv file parsed (if found).
  """

  getthis_mapping = {}
  
  result = {
    'volstat':  {}
  }

  # Open archive
  try:
    if archive_name in archives_with_password.keys():
      archive = SevenZipFile(archive, password=archives_with_password[archive_name])
    else:
      archive = SevenZipFile(archive)
  except Bad7zFile:
    logging.warning('%s is not a valid 7z file', archive_name)
    return False

  # Read all the archive content
  files = archive.readall()

  # Check if there is a GetThis.csv and get its content
  if 'GetThis.csv' in files.keys():
    getthis_mapping = _parse_getthis(files['GetThis.csv'], destination_folder)
  
  # Check if there is a volstats.csv and get its content
  if 'volstats.csv' in files.keys():
    result['volstat'] = _parse_volstats(files['volstats.csv'])


  # Itterate on each file
  for filename, file_content in files.items():

    # Write the Artefact if in GetThis.csv and log if something went wrong
    if filename in getthis_mapping.keys():
      if not _write_file(getthis_mapping[filename]['path'], file_content, mtime=getthis_mapping[filename]['mtime'], atime=getthis_mapping[filename]['atime']):
        log_file_with_artefacts_non_extracted.write(f'{archive_name},{filename},{getthis_mapping[filename]}\n')

    # Write the report file and log if something went wrong
    elif f'{archive_name}/{filename}' in report_files:
      if not _write_file(report_destination_directory.joinpath(filename), file_content):
        log_file_with_artefacts_non_extracted.write(f'{archive_name},{filename},{report_destination_directory.joinpath(filename)}\n')
  
    # Rerun on sub 7z folder.
    elif filename.endswith('.7z'):
      sub_call_result = _extract_artefacts_recusrive(
        file_content,
        destination_folder,
        log_file_with_artefacts_non_extracted,
        archive_name=filename,
        archives_with_password=archives_with_password,
        report_files=report_files,
        report_destination_directory=report_destination_directory
      )

      if sub_call_result:
        # Merge sub call results
        ## We merge the volstat result from sub call with the ones of this call. Rewrite this call result with subcall result.
        result['volstat'] = {**result['volstat'], **sub_call_result['volstat']}

  archive.close()

  return result

def _rename_volumes(
  destination_folder: pathlib.Path,
  volumeid_mapped_to_drive_letter: dict
) -> None:
  """
  This function replaces each VolumeID by its matching mounted drive letter for each folder in `destination_folder`.

  The `volumeid_mapped_to_drive_letter` should be the result of the `_parse_volstats` function during the execution of `_extract_artefacts_recusrive`.

  Args:
    destination_folder: The destination path where to save artefacts.
    volumeid_mapped_to_drive_letter: A dictionnary containing a mapping from VolumeID with their respective mounted drive letter.
  """

  # For each Volume ID in volumeid_mapped_to_drive_letter
  for volume_id in volumeid_mapped_to_drive_letter.keys():

    # Check for folder in `destination_folder` starting with the Volume ID
    for dir in destination_folder.glob(f'{volume_id}*'):
      
      # And rename the folder, with a new name (we specify the full path as pathlib.rename assumes relative pathes are under the working directory and not the filepath root parent) 
      dir.rename(destination_folder.joinpath(dir.name.replace(volume_id, volumeid_mapped_to_drive_letter[volume_id]))) 


def artefact_rebuilder( 
  archive_path: pathlib.Path,
  destination_folder: pathlib.Path,
  configuration_file_path: pathlib.Path = None,
  rename_volumes: bool = True
) -> None:
  """
  Extract all artefacts from a DFIR-Orc archive by re-building their original path and extension

  Args:
    archive_path: DFIR-Orc archive file (7z).
    destination_folder: The destination path where to save artefacts.
    configuration_file_path: The configuration file to use.
    rename_volumes: Indicates if the function should rename the volumes.
  """

  log_path_of_artefacts_non_extracted = destination_folder.joinpath('artefacts_non_extracted.csv')
  archives_with_password = {}
  report_files = []
  report_destination_directory = None
  extract_results = {}

  # If destination_folder doesn't exists, creates it
  destination_folder.mkdir(exist_ok=True)

  # Load configuration if any.
  if configuration_file_path:
    with open(configuration_file_path, "rb") as configuration_fd:
      configuration = tomllib.load(configuration_fd)

      archives_with_password = configuration['protected']['sub_archive']
      report_files = configuration['reports']['filenames']

      # Create the directory where to put reports
      report_destination_directory = destination_folder.joinpath(configuration['reports']['target_directory'])
      report_destination_directory.mkdir(exist_ok=True)

  # Open the logging file and start archive extraction
  with open(log_path_of_artefacts_non_extracted, 'w') as log_file_of_artefacts_non_extracted:

    log_file_of_artefacts_non_extracted.write('Archive Name,Artefact Name,Expected Target Path\n')
    
    extract_results = _extract_artefacts_recusrive(
      archive_path,
      destination_folder,
      log_file_of_artefacts_non_extracted,
      archive_name='.',
      archives_with_password=archives_with_password,
      report_files=report_files,
      report_destination_directory=report_destination_directory
    )

  # Rename volumes with mapped letter
  if rename_volumes:
    _rename_volumes(destination_folder, extract_results['volstat'])

  return True

# Main function
if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(prog = 'DFIR-ORC Archive Rebuilder', description=__doc__, epilog=epilog_doc, formatter_class=argparse.RawDescriptionHelpFormatter)

  parser.add_argument('orc_archive', help='The 7z DFIR-Orc ouptut archive', type=argparse.FileType('rb'))
  
  parser.add_argument('destination_folder', help='The folder where to save the artefacts', type=pathlib.Path)

  parser.add_argument('-c', '--conf', '--conf-file', help='The folder where to save the artefacts', type=argparse.FileType('rb'))

  args = parser.parse_args()

  artefact_rebuilder(args.orc_archive, args.destination_folder, configuration_file_path=args.conf.name)
