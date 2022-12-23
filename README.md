# orc-archive-rebuilder

Get all collected artefacts from DFIR-Orc output 7z file and extract them by re-building their original path and extension.  
The aim of this tool is to be able to run parsers which rely on file path and extension like Kape or Plaso.  
The script check for each GetThis.csv file in sub directories, and extract each file listed inside.  
You can also configure the tool to extract specific files, based on your DFIR-ORC configuration (like autoruns.csv from the DFIR-ORC config sample).  

Known limitations:

  - Parsers which rely on filestat may give wrong output and macb reflects the script running time. (explore os.utime or atomicredteam)
  - This tool fails to extract artefacts if the targeted filepath is bigger than the OS lenght limitation.

## Install
Use pip and git directly.

```
pip install git+https://github.com/nahotjan/dfir-orc-archive-rebuilder.git
```

This install will run ./setup.py, installing requirments and add to your path dfir-orc-archive-rebuilder.py

The script is currently a standalone so you also download and run it manually. 

## Usage
```
dfir-orc-archive-rebuilder.py /path/to/dfir-orc-collection.7z /path/to/analyze/machinexyz -c .\sample.toml
```

The script will create the destination folder (here machinexyz) if not existing. The script write, inside this destination folder, all files retrieved via GetThis command with their source path. Check Output exemple for more details.

The parameter `-c .\sample.toml` point to a configuration file (optionnal), to enable and configure some features;

  - Extraction of files from external command runs (like the autoruns.csv file from DFIR-ORC standard configuration)
  - Openning of 7z subfolders containing artefacts and password protected (to bypass AV scanning)

Please refer to sample.toml for more details.

## Output exemple

The script output exemple could be:

```
<destination_path>
   ├─ reports
   |  └─ autoruns.csv
   ├─ C
   |  ├─ Program Files
   |  ├─ Users
   |  ...
   |  └─ Windows
   ├─ C (vsc {SNAPSHOT ID})
   |  ├─ ...
   |  └─ ...
   |─ D
   |  ├─ ...
   |  └─ ...
   └─ artefacts_non_extracted.csv
```

The drive letters are obtained if the DFIR-ORC archive contains a volstats.csv file with volumeID and their mapped mounted drive. If not folders will keep their VolumeID.

## Contribution

The project is open for contribution and feature requests as soon as they are helpfull for the community.  
Please comment and make the code as understandable as possible to allow code review and contribution.
