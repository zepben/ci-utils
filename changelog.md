# CI-Utils
## [6.24.0] - UNRELEASED
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.23.0] - 2025-09-30
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.22.0] - 2025-09-19
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.21.0] - 2025-09-16
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* Few enhancements for the Docusaurus pipeline - build script improved.

### Fixes
* None.

### Notes
* None.

## [6.20.0] - 2025-08-06
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.19.0] - 2025-08-05
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.18.0] - 2025-07-30
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.17.0] - 2025-07-29
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.16.0] - 2025-07-22
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.15.0] - 2025-07-17
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.14.0] - 2025-07-17
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.13.0] - 2025-07-17
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.12.0] - 2025-07-16
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* Fix sed pattern for removing 'b' from snapshots in maven builds, again.

### Notes
* None.

## [6.11.0] - 2025-07-11
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* Fix sed pattern for removing 'b' from snapshots in maven builds.

### Notes
* None.

## [6.10.0] - 2025-07-11
### Breaking Changes
* Change the `-SNAPSHOT` nomenclature for the snapshots in maven to `b`. This aligns with python pattern but breaks all maven snapshot builds.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.9.0] - 2025-07-10
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* Added debug message to indicate we're building for Docusaurus2.
* Change "skip-build" param to "--skip-build" 

### Fixes
* None.

### Notes
* None.

## [6.8.0] - 2025-07-10
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.7.0] - 2025-07-09
### Breaking Changes
* None.

### New Features
* Add Docusaurus pipeline, workflow and test scripts.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.6.0] - 2025-05-16
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* test.

## [6.5.0] - 2025-04-29
### Breaking Changes
* None.

### New Features
* Install GH on `pipeline-java`

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.4.0] - 2025-02-10
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* Rename version and commit labels to include the type of the container; ie `pipeline-basic-commit` or `pipeline-java-version`.

### Fixes
* None.

### Notes
* None.

## [6.3.0] - 2025-02-07
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* run() command (from `common.sh`) disables `set -e` temporarily for its run; it's needed so that it can proceed on errors.

### Fixes
* None.

### Notes
* None.

## [6.2.0] - 2025-02-06
### Breaking Changes
* None.

### New Features
* Add libxml2-utils to java pipeline container

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [6.1.0] - 2025-02-05
### Breaking Changes
* None

### New Features
* None.

### Enhancements
* Clear the release branch if it exists during release checks.
* Add labels to the pipeline containers

### Fixes
* None.

### Notes
* None.

## [6.0.0] - October 24, 2024
### Breaking Changes
* Rebuild the way containers are created - all containers are latest + tag; only tag if in testing.

### New Features
* None.

### Enhancements
* None.

### Fixes
* None.

### Notes
* None.

## [5.7.5] - October 4, 2024 
### Breaking Changes
* None.

### New Features
* None.

### Enhancements
* None.

### Fixes
* Variable type fixed for version comparison.

### Notes
* None.

