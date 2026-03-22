# ArtistsSearchSearchV1ArtistsGetParameters

**Properties**

| Name    | Type   | Required | Description                                                                                                                                                                                                                             |
| :------ | :----- | :------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q       | String | ✅       | Search query text                                                                                                                                                                                                                       |
| count   | Long   | ❌       | The number of results returned in the response                                                                                                                                                                                          |
| genreId | String | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/ |
