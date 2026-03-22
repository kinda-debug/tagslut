# TracksDefaultModel

**Properties**

| Name                    | Type                                                            | Required | Description |
| :---------------------- | :-------------------------------------------------------------- | :------- | :---------- |
| score                   | Double                                                          | ✅       |             |
| addDate                 | String                                                          | ✅       |             |
| artists                 | List<[TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)> | ✅       |             |
| availableWorldwide      | Long                                                            | ✅       |             |
| changeDate              | String                                                          | ✅       |             |
| currentStatus           | [CurrentStatusModel](CurrentStatusModel.md)                     | ✅       |             |
| enabled                 | Long                                                            | ✅       |             |
| encodeStatus            | String                                                          | ✅       |             |
| exclusivePeriod         | Long                                                            | ✅       |             |
| genreEnabled            | Long                                                            | ✅       |             |
| isAvailableForStreaming | Long                                                            | ✅       |             |
| isClassic               | Long                                                            | ✅       |             |
| label                   | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)         | ✅       |             |
| labelManager            | String                                                          | ✅       |             |
| mixName                 | String                                                          | ✅       |             |
| publishDate             | String                                                          | ✅       |             |
| publishStatus           | String                                                          | ✅       |             |
| release                 | [TrackReleaseModel](TrackReleaseModel.md)                       | ✅       |             |
| releaseDate             | String                                                          | ✅       |             |
| saleType                | String                                                          | ✅       |             |
| suggest                 | [TrackSuggestModel](TrackSuggestModel.md)                       | ✅       |             |
| supplierId              | Long                                                            | ✅       |             |
| trackId                 | Long                                                            | ✅       |             |
| trackName               | String                                                          | ✅       |             |
| trackNumber             | Long                                                            | ✅       |             |
| updateDate              | String                                                          | ✅       |             |
| wasEverExclusive        | Long                                                            | ✅       |             |
| bpm                     | Long                                                            | ❌       |             |
| catalogNumber           | String                                                          | ❌       |             |
| chordTypeId             | Long                                                            | ❌       |             |
| exclusiveDate           | String                                                          | ❌       |             |
| freeDownloadEndDate     | String                                                          | ❌       |             |
| freeDownloadStartDate   | String                                                          | ❌       |             |
| guid                    | String                                                          | ❌       |             |
| isrc                    | String                                                          | ❌       |             |
| keyId                   | Long                                                            | ❌       |             |
| keyName                 | String                                                          | ❌       |             |
| length                  | Long                                                            | ❌       |             |
| preOrderDate            | String                                                          | ❌       |             |
| streamingDate           | String                                                          | ❌       |             |
| downloads               | Long                                                            | ❌       |             |
| plays                   | Long                                                            | ❌       |             |
| price                   | [PriceModel](PriceModel.md)                                     | ❌       |             |
| isExplicit              | Boolean                                                         | ❌       |             |
| isAvailableForAlacarte  | Boolean                                                         | ❌       |             |
| isDjEdit                | Boolean                                                         | ❌       |             |
| isUgcRemix              | Boolean                                                         | ❌       |             |
| isPreOrder              | Boolean                                                         | ❌       |             |
| trackImageUri           | String                                                          | ❌       |             |
| trackImageDynamicUri    | String                                                          | ❌       |             |
| genre                   | TracksDefaultModelGenre                                         | ❌       |             |
| subGenre                | [SubGenreModel](SubGenreModel.md)                               | ❌       |             |
