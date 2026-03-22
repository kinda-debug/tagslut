# ChartsDefaultModel

**Properties**

| Name                 | Type                              | Required | Description |
| :------------------- | :-------------------------------- | :------- | :---------- |
| score                | Double                            | ✅       |             |
| chartId              | Long                              | ✅       |             |
| chartName            | String                            | ✅       |             |
| createDate           | String                            | ✅       |             |
| isApproved           | Long                              | ✅       |             |
| updateDate           | String                            | ✅       |             |
| enabled              | Long                              | ✅       |             |
| isIndexed            | Long                              | ✅       |             |
| isPublished          | Long                              | ✅       |             |
| artistId             | Long                              | ❌       |             |
| artistName           | String                            | ❌       |             |
| personId             | Long                              | ❌       |             |
| publishDate          | String                            | ❌       |             |
| itemTypeId           | Long                              | ❌       |             |
| personUsername       | String                            | ❌       |             |
| trackCount           | Long                              | ❌       |             |
| chartImageUri        | String                            | ❌       |             |
| chartImageDynamicUri | String                            | ❌       |             |
| genres               | List<[GenreModel](GenreModel.md)> | ❌       |             |
