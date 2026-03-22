# ReleasesDefaultModel

**Properties**

| Name                   | Type                                                        | Required | Description |
| :--------------------- | :---------------------------------------------------------- | :------- | :---------- |
| score                  | number                                                      | ✅       |             |
| label                  | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)     | ✅       |             |
| aggregator             | [ReleaseAggregatorModel](ReleaseAggregatorModel.md)         | ✅       |             |
| availableWorldwide     | number                                                      | ✅       |             |
| exclusive              | number                                                      | ✅       |             |
| publishDate            | string                                                      | ✅       |             |
| releaseDate            | string                                                      | ✅       |             |
| releaseId              | number                                                      | ✅       |             |
| releaseName            | string                                                      | ✅       |             |
| releaseType            | string                                                      | ✅       |             |
| status                 | number                                                      | ✅       |             |
| updateDate             | string                                                      | ✅       |             |
| currentStatus          | [CurrentStatusModel](CurrentStatusModel.md)[]               | ❌       |             |
| genre                  | ReleasesDefaultModelGenre                                   | ❌       |             |
| tracks                 | [ReleaseTrackModel](ReleaseTrackModel.md)[]                 | ❌       |             |
| key                    | [ReleaseKeyModel](ReleaseKeyModel.md)[]                     | ❌       |             |
| artists                | [TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)[] | ❌       |             |
| catalogNumber          | string                                                      | ❌       |             |
| createDate             | string                                                      | ❌       |             |
| encodedDate            | string                                                      | ❌       |             |
| exclusiveDate          | string                                                      | ❌       |             |
| streamingDate          | string                                                      | ❌       |             |
| preorderDate           | string                                                      | ❌       |             |
| labelManager           | string                                                      | ❌       |             |
| preOrderDate           | string                                                      | ❌       |             |
| upc                    | string                                                      | ❌       |             |
| price                  | [PriceModel](PriceModel.md)                                 | ❌       |             |
| isExplicit             | boolean                                                     | ❌       |             |
| trackCount             | number                                                      | ❌       |             |
| releaseImageUri        | string                                                      | ❌       |             |
| releaseImageDynamicUri | string                                                      | ❌       |             |
| downloads              | number                                                      | ❌       |             |
| isHype                 | boolean                                                     | ❌       |             |
| isPreOrder             | boolean                                                     | ❌       |             |
| plays                  | number                                                      | ❌       |             |

# ReleasesDefaultModelGenre
