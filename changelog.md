# CI-Utils
## [6.5.0] - UNRELEASED
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

