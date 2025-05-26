# Zepben Powerfactory Exporter changelog
## [0.7.0] - UNRELEASED
### Breaking Changes
- None.

### Added
- Processor controller to aggregate all processors
- Feeder Colour processor
- ciorient variable to ElmFeeder
- LoadSiteProcessor added to create ElmTrfstat for each ElmLod and assign them to the ElmTrfstat
- DefaultLoadProcessor added to give all ElmLod a default load
- RecloserProcessor added to untangle square network with jumbled connectivity node
- StarPointProcessor added to allow application of r0 and x0 values to distribution transformers
- Phases are now properly mapped to all elements
- ElementGapperProcessor added to provide gapping between elements and flanking lines in PF
- PhaseCode.N will be properly mapped to PhaseTechnology.N
- ElmShnt is created for LinearShuntCompensator
- Added missing test for Elmsubstat in MappingsTest
- A geographic IntGrfnet will be created as the final step of dgs.convert as default diagram
- Implement voltage regulator mapping
- Feeder colour added to demo_config
- Implement neutral assignment to fuse
- Jumpers are now mapped
- Added a final processor to clean up unused elements in dgs
- Added a processor to process distribution transformers site
- Terminals are now sorted by feeder direction before running it through stacubic creation
- Added Current Transformer mapping
- Added PhaseRotation enum for power factory
- Map PowerElectronicsConnection to ElmPVsys
- Added Time series database support for Elmload loadflow values
- HV Customer data are now read in for max load distribution
- Distribution Transformer will now inherit Tap changer value from Transformer end one
- Added a processor to change Elmcoup aUsage base on its chrname for endeavour's custom symbol
- Added sType for ElmTrfstat to further investigate custom symbol options
- Energy Source Impedance mapping
- ElmxNet Processor to remove external grids without source impedance
- Added Switch typing for LVLINK switches
- Added TypLod for general load type mapping
- Added Processor to remove hanging ElmCoup and RelFuse
- Auxiliary Equipments are now removed as part of the final clean up process
- snss and snssmin value removed from ElmXnet to prevent default value being written out or inconsistency with official document
- Enabled SWER transformer mapping as per Endevor's way, this should be changed when SWER works properly in PF.
- Model name is generated during model creation if one wasn't given
- Added ElmVac object type
- CharactersticApproximation and DatabaseUsage Enum added for time characteristic variable
- Circuits are now supported as part of the model process to create Sub-trans models
- Sites are now mapped to Elmsite instead of ElmTrfstat
- TransformerSiteType added for custom symbol purposes
- Final clean up will inlcude StaCt as part of its clean up
- Added a processor that change all LV Elmterm UkNom value to 400
- SubtransConsolidationProcessor added for consistency like LvConsolidation
- Add in TriSwitchProcessor to clean up tri switch set up on maps
- Added mapping for a few shunt capacitor variables
- Added excited current and zero impedance loss for typtr2 mapping
- Added mapping for 3 winding transformers
- Energy consumer in zone sub now mapped as Complex loads
- Neutral switches are mapped as ElmGndswt
- Add Docusaurus docs

### Changed
- ElmSubstrat now gets a foldId assignment
- assignment of new gps location in recloser processor has been moved so entries are only modified if recloser structural change has passed
- Busbar now work off its description to find the correct connectivity node.
- Lower element gapper added distance
- Switch phase technology now depends on switch's own terminal (maximum phase num)
- Elmcoup and Relfuse nNeutral assignment changed (technically same result but goes off N in phases)
- Voltage regulator mapping enabled
- LV side rated current is hard set to 0.5 for single phase transformers
- Default value for defalut load is changed to be more reasonable
- Typlne FID will now take base voltage into consideration.
- Updated exporter to support the creation of simplified networks at the edge of requested networks 
- Locname and Chrname for Elmcoup and Elmterm (Busbars) will now map off object nametypes
- Defaulloadprocessor accomodates for equivalent branch energy consumers
- Calculation for load is done in volt instead of KV
- File intake for maxload is now limited to csv instead of accepting Excel files
- Elmlne now inherit line type to its description for Custom Labels
- Added more attributes to ElmTr2 and ElmXnet
- We now pass in two clients (one for mapping one for info) for network processing before DGS mapping
- Power Transformer in substation now tap changes at LV side with Positive Sequence (from HV side and A phase only)
- Changed Test coverage to 0.69 because it will be too much wasted effort in creating a functional DgsGenerator Test.
- Default load will be assigned to Elmlod when entries are not found in Maxfeederload file
- DTX busbar processor now account for padmount set up
- database processor will now check against a nmi list file to determine which energy consumer to create database link for 
- Made changes to typtr2 mapping to reflect power transformer end sRating changes in the importer and SDK.
- Energysource now map to ElmVac until power factory fix ElmXnet value discrepancy
- Substation of requested feeders will always be included in the model
- Database Table name changed from readings to samples.
- ElmLod inputmode has been expanded to support all mode in power factory
- A Reference file is written for all nmi even when they are not in the list
- Nmi not in the list will be linked to AVG Time characteristic as default
- Approximation of Time Characteristic now changed from absolute to Linear
- LVnetworks are now consolidated into HV, so they don't create their own grid
- Introduce a processor to sort "SP" connectivity_nodes into corresponding substation
- desc as a variable is moved to Element so everything can have description
- getPowerTransformerNumberOfPhases method moved to DgsNetworkUtilis
- ElmLod will accumulate associated NMI as their description
- Enhanced Element Gapper
- Recloser processor now works with volt Reg since they are normally in a site with similar set up. We also no longer 
  process recloser that's not connected on both side
- GPSLon and GPSLat moved from individual ServiceElement to the parent class
- Switch that is directly connected to load in a site is moved into the load site to clean things up.
- LvElmTermProcessor will now also work when there is no LvFeeder requested.
- Subtrans model will now derive their name from loops instead of circuits.
- Changed database objects naming convention to prevent fID being too long
- Symbol for substation sites are now determined by transformer construction kind instead of name types
- Changed how energy source is added to the network, only keep new source if source impedance value transferred over
- Energy Source with no source impedance will not be removed during final clean up
- Site foldID mapping now goes off a priority system of PT feeder, then equipment feeder, then finally circuit.
- Energy Source (ElmVac) will be disabled in Zone subs when BSP exists in the model.

### Fixed
- findGPSForCNN method now ignores connectivity nodes with a single terminal
- TypLne correctly use cOhl and not aOhl(not a PF variable)
- Load site are now assigned to the network and have its loc_name changed
- Recloser switch type is changed to circuit breaker
- Recloser processor changed up to accommodate skipped recloser from importer
- Relfuse and Elmcoup now accommodates for N phase only switches
- Change from First to FirstorNull in elementaGapper, so it can be by pass if elements are missing.
- Renamed test file to properly reflect its function
- We now handle any mRID above 40 character by generating new UUID for it
- duTap setting of Typtr2 now put behind a null check to prevent errors
- Substation transformers are now grounded
- Stacubic now maps phase changes properly when it occurs
- Exclude StaCt from final clean up as current transformers are attached to a terminal of another conducting equipment, thus it does not have a StaCubic referencing it.
- chrname truncate for elmcoup now properly set to 20
- Added missing Relfuse mapping test from custom label changes
- Patched Remove External Grid function to prevent concurrent errors
- Busbar assignment for Distribution transformer site has been corrected for HV side
- Conducting Equipment belonging to two container will now be checked against requested container mRID before removing from the network
- Power Transformer impedance calculation corrected
- Remove external grid will only occur when new energy sources are added
- Element Gapper will now ignore elements with no co-ord points properly
- chrname and locname of elmcoup will now have invalid characters removed
- Remove Hanging Element will now crosscheck switch with feeder head to ensure feeder head equipment is not removed
- nntap will be checked in typtr2 to be between ntmpn and ntpmx
- chrname and foldid had added checks if they are assigned through networkservice objects
- Isolation transformer value and flanking Elmterm or Stacubic is corrected
- Introduce Double.Nan check for transformer source impedance value
- Stacubic and Elmterm association is now updated in the dgsservice list in recloser processor.
- Correct the math on the calculation of the ikss value of ElmXnet
- iintgnd value fix for DTX (ElmTr2)
- ikssmin calculation fix for ElmXNet
- RemoveHangingElmCoup will now ignore elements with auxiliary equipment attached
- ElmSubstat type sorting fixed to prevent spelling issue
- Remove the chance for final file name to be blank
- HVC equipments and connectivity nodes are properly sorted
- Power Transformer end will now properly filter out NaN instead of writing it out to cause a mistake
- Fixed power transformer Impedance math
- Added check for element gapper to prevent movement if part of the switch group is not on the map
- Fixed power transformer source impedance values
- 3 winding transformer impedance math to take in consideration of ratedS ratio and mapping refined
- Fix cneutcon for Power transformer containing neutral grounding connection in substation
- Fix elmTerm detail between neutral terminal and grounding switch
- Auxiliary equipment removal doesn't remove equipment with 0 voltage
- Elemental gapper ignores Line-Switch-Switch-Line formation that doesn't end up with 2 new position points.
- Fix iintgnd and hv/lv ground connection so neutral connect is correctly assigned on import
- MV end from 3 winding power transformer will also have its ratedS ratioed.

### Removed
- None.

### Notes
- None.

## [0.6.0] - 2022-08-30
### Breaking Changes
- None.

### Added
- None.

### Changed
- None.

### Fixed
- None.

### Removed
- None.

### Notes
- None.

## [0.5.0] - 2022-08-05
### Breaking Changes
- None.

### Added
- None.

### Changed
- None.

### Fixed
- None.

### Removed
- None.

### Notes
- None.

## [0.4.0] - 2022-08-05
### Breaking Changes
- None.

### Added
- None.

### Changed
- None.

### Fixed
- None.

### Removed
- None.

### Notes
- None.


## [0.3.0] - 2022-08-04
##### Breaking Changes
* None.

##### New Features
* None.

##### Enhancements
* None.

##### Fixes
* None.

##### Notes
* None.
