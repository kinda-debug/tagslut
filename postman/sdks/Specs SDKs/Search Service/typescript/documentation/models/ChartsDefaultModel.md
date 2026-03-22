# ChartsDefaultModel

**Properties**

| Name                 | Type                          | Required | Description |
| :------------------- | :---------------------------- | :------- | :---------- |
| score                | number                        | ✅       |             |
| chartId              | number                        | ✅       |             |
| chartName            | string                        | ✅       |             |
| createDate           | string                        | ✅       |             |
| isApproved           | number                        | ✅       |             |
| updateDate           | string                        | ✅       |             |
| enabled              | number                        | ✅       |             |
| isIndexed            | number                        | ✅       |             |
| isPublished          | number                        | ✅       |             |
| artistId             | number                        | ❌       |             |
| artistName           | string                        | ❌       |             |
| personId             | number                        | ❌       |             |
| publishDate          | string                        | ❌       |             |
| itemTypeId           | number                        | ❌       |             |
| personUsername       | string                        | ❌       |             |
| trackCount           | number                        | ❌       |             |
| chartImageUri        | string                        | ❌       |             |
| chartImageDynamicUri | string                        | ❌       |             |
| genres               | [GenreModel](GenreModel.md)[] | ❌       |             |
