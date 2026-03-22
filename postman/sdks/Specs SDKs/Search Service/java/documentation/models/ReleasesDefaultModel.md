# ReleasesDefaultModel

**Properties**

| Name                   | Type                                                            | Required | Description |
| :--------------------- | :-------------------------------------------------------------- | :------- | :---------- |
| score                  | Double                                                          | ✅       |             |
| label                  | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)         | ✅       |             |
| aggregator             | [ReleaseAggregatorModel](ReleaseAggregatorModel.md)             | ✅       |             |
| availableWorldwide     | Long                                                            | ✅       |             |
| exclusive              | Long                                                            | ✅       |             |
| publishDate            | String                                                          | ✅       |             |
| releaseDate            | String                                                          | ✅       |             |
| releaseId              | Long                                                            | ✅       |             |
| releaseName            | String                                                          | ✅       |             |
| releaseType            | String                                                          | ✅       |             |
| status                 | Long                                                            | ✅       |             |
| updateDate             | String                                                          | ✅       |             |
| currentStatus          | List<[CurrentStatusModel](CurrentStatusModel.md)>               | ❌       |             |
| genre                  | ReleasesDefaultModelGenre                                       | ❌       |             |
| tracks                 | List<[ReleaseTrackModel](ReleaseTrackModel.md)>                 | ❌       |             |
| key                    | List<[ReleaseKeyModel](ReleaseKeyModel.md)>                     | ❌       |             |
| artists                | List<[TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)> | ❌       |             |
| catalogNumber          | String                                                          | ❌       |             |
| createDate             | String                                                          | ❌       |             |
| encodedDate            | String                                                          | ❌       |             |
| exclusiveDate          | String                                                          | ❌       |             |
| streamingDate          | String                                                          | ❌       |             |
| preorderDate           | String                                                          | ❌       |             |
| labelManager           | String                                                          | ❌       |             |
| preOrderDate1          | String                                                          | ❌       |             |
| upc                    | String                                                          | ❌       |             |
| price                  | [PriceModel](PriceModel.md)                                     | ❌       |             |
| isExplicit             | Boolean                                                         | ❌       |             |
| trackCount             | Long                                                            | ❌       |             |
| releaseImageUri        | String                                                          | ❌       |             |
| releaseImageDynamicUri | String                                                          | ❌       |             |
| downloads              | Long                                                            | ❌       |             |
| isHype                 | Boolean                                                         | ❌       |             |
| isPreOrder             | Boolean                                                         | ❌       |             |
| plays                  | Long                                                            | ❌       |             |
