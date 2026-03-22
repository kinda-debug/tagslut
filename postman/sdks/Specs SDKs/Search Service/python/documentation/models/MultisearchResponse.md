# MultisearchResponse

Response model for the `all-search` endpoint.

**Properties**

| Name     | Type                                    | Required | Description                                 |
| :------- | :-------------------------------------- | :------- | :------------------------------------------ |
| tracks   | [TracksResponse](TracksResponse.md)     | ✅       | Response model for the `tracks` endpoint.   |
| artists  | [ArtistsResponse](ArtistsResponse.md)   | ✅       |                                             |
| charts   | [ChartsResponse](ChartsResponse.md)     | ✅       |                                             |
| labels   | [LabelsResponse](LabelsResponse.md)     | ✅       |                                             |
| releases | [ReleasesResponse](ReleasesResponse.md) | ✅       | Response model for the `releases` endpoint. |
