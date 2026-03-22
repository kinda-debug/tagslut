# TracksDefaultModel

**Properties**

| Name                    | Type                                                        | Required | Description |
| :---------------------- | :---------------------------------------------------------- | :------- | :---------- |
| score                   | number                                                      | ✅       |             |
| addDate                 | string                                                      | ✅       |             |
| artists                 | [TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)[] | ✅       |             |
| availableWorldwide      | number                                                      | ✅       |             |
| changeDate              | string                                                      | ✅       |             |
| currentStatus           | [CurrentStatusModel](CurrentStatusModel.md)                 | ✅       |             |
| enabled                 | number                                                      | ✅       |             |
| encodeStatus            | string                                                      | ✅       |             |
| exclusivePeriod         | number                                                      | ✅       |             |
| genreEnabled            | number                                                      | ✅       |             |
| isAvailableForStreaming | number                                                      | ✅       |             |
| isClassic               | number                                                      | ✅       |             |
| label                   | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)     | ✅       |             |
| labelManager            | string                                                      | ✅       |             |
| mixName                 | string                                                      | ✅       |             |
| publishDate             | string                                                      | ✅       |             |
| publishStatus           | string                                                      | ✅       |             |
| release                 | [TrackReleaseModel](TrackReleaseModel.md)                   | ✅       |             |
| releaseDate             | string                                                      | ✅       |             |
| saleType                | string                                                      | ✅       |             |
| suggest                 | [TrackSuggestModel](TrackSuggestModel.md)                   | ✅       |             |
| supplierId              | number                                                      | ✅       |             |
| trackId                 | number                                                      | ✅       |             |
| trackName               | string                                                      | ✅       |             |
| trackNumber             | number                                                      | ✅       |             |
| updateDate              | string                                                      | ✅       |             |
| wasEverExclusive        | number                                                      | ✅       |             |
| bpm                     | number                                                      | ❌       |             |
| catalogNumber           | string                                                      | ❌       |             |
| chordTypeId             | number                                                      | ❌       |             |
| exclusiveDate           | string                                                      | ❌       |             |
| freeDownloadEndDate     | string                                                      | ❌       |             |
| freeDownloadStartDate   | string                                                      | ❌       |             |
| guid                    | string                                                      | ❌       |             |
| isrc                    | string                                                      | ❌       |             |
| keyId                   | number                                                      | ❌       |             |
| keyName                 | string                                                      | ❌       |             |
| length                  | number                                                      | ❌       |             |
| preOrderDate            | string                                                      | ❌       |             |
| streamingDate           | string                                                      | ❌       |             |
| downloads               | number                                                      | ❌       |             |
| plays                   | number                                                      | ❌       |             |
| price                   | [PriceModel](PriceModel.md)                                 | ❌       |             |
| isExplicit              | boolean                                                     | ❌       |             |
| isAvailableForAlacarte  | boolean                                                     | ❌       |             |
| isDjEdit                | boolean                                                     | ❌       |             |
| isUgcRemix              | boolean                                                     | ❌       |             |
| isPreOrder              | boolean                                                     | ❌       |             |
| trackImageUri           | string                                                      | ❌       |             |
| trackImageDynamicUri    | string                                                      | ❌       |             |
| genre                   | TracksDefaultModelGenre                                     | ❌       |             |
| subGenre                | [SubGenreModel](SubGenreModel.md)                           | ❌       |             |

# TracksDefaultModelGenre
