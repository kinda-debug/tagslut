# SearchEndpointsService

A list of all methods in the `SearchEndpointsService` service. Click on the method name to view detailed information about that method.

| Methods                                                                 | Description                                   |
| :---------------------------------------------------------------------- | :-------------------------------------------- |
| [tracksSearchSearchV1TracksGet](#trackssearchsearchv1tracksget)         | Returns a set of track results                |
| [releasesSearchSearchV1ReleasesGet](#releasessearchsearchv1releasesget) | Returns a set of release results              |
| [artistsSearchSearchV1ArtistsGet](#artistssearchsearchv1artistsget)     | Returns a set of artist results               |
| [labelsSearchSearchV1LabelsGet](#labelssearchsearchv1labelsget)         | Returns a set of label results                |
| [chartsSearchSearchV1ChartsGet](#chartssearchsearchv1chartsget)         | Returns a set of chart results                |
| [allSearchSearchV1AllGet](#allsearchsearchv1allget)                     | Returns a set of results for all search types |

## tracksSearchSearchV1TracksGet

Returns a set of track results

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name                    | Type    | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                               |
| :---------------------- | :------ | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| q                       | string  | ✅       | Search query text                                                                                                                                                                                                                                                                                                                                                                                                         |
| count                   | number  | ❌       | The number of results returned in the response                                                                                                                                                                                                                                                                                                                                                                            |
| preorder                | boolean | ❌       | When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status                                                                                                                                                                                                                                                                        |
| fromPublishDate         | string  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                      |
| toPublishDate           | string  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                      |
| fromReleaseDate         | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| toReleaseDate           | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| genreId                 | string  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                                                                                                                                                                   |
| genreName               | string  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/                                                                                                                                              |
| mixName                 | string  | ❌       | Search for a specific mix name, ex: original                                                                                                                                                                                                                                                                                                                                                                              |
| fromBpm                 | number  | ❌       |                                                                                                                                                                                                                                                                                                                                                                                                                           |
| toBpm                   | number  | ❌       |                                                                                                                                                                                                                                                                                                                                                                                                                           |
| keyName                 | string  | ❌       | Search for a specific key in the following format: A Major, A Minor, A# Major, A# Minor, Ab Major, Ab Minor                                                                                                                                                                                                                                                                                                               |
| mixNameWeight           | number  | ❌       | This parameter determines how much weight to put on mix_name using the search query text from q. The higher the value the more weight is put on matching q to mix_name                                                                                                                                                                                                                                                    |
| labelNameWeight         | number  | ❌       | This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name                                                                                                                                                                                                                                                |
| djEdits                 | boolean | ❌       | When FALSE, the response will exclude DJ Edit tracks. When TRUE, the response will return only DJ Edit tracks.                                                                                                                                                                                                                                                                                                            |
| ugcRemixes              | boolean | ❌       | When FALSE, the response will exclude UGC Remix tracks. When TRUE, the response will return only UGC Remix tracks.                                                                                                                                                                                                                                                                                                        |
| djEditsAndUgcRemixes    | boolean | ❌       | When FALSE, the response will exclude DJ Edits and UGC Remix tracks. When TRUE, the response will return only DJ Edits or UGC Remix tracks. When parameter is not included, the response will include DJ edits and UGC remixes amongst other tracks.                                                                                                                                                                      |
| isAvailableForStreaming | boolean | ❌       | By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming. |

**Return Type**

`TracksResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.tracksSearchSearchV1TracksGet({
    q: 'q',
    count: 20,
    preorder: true,
    fromPublishDate: 'from_publish_date',
    toPublishDate: 'to_publish_date',
    fromReleaseDate: 'from_release_date',
    toReleaseDate: 'to_release_date',
    genreId: 'genre_id',
    genreName: 'genre_name',
    mixName: 'mix_name',
    fromBpm: 9,
    toBpm: 2,
    keyName: 'key_name',
    mixNameWeight: 1,
    labelNameWeight: 1,
    djEdits: true,
    ugcRemixes: true,
    djEditsAndUgcRemixes: true,
    isAvailableForStreaming: true,
  });

  console.log(data);
})();
```

## releasesSearchSearchV1ReleasesGet

Returns a set of release results

- HTTP Method: `GET`
- Endpoint: `/search/v1/releases`

**Parameters**

| Name              | Type    | Required | Description                                                                                                                                                                                                                                                                  |
| :---------------- | :------ | :------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q                 | string  | ✅       | Search query text                                                                                                                                                                                                                                                            |
| count             | number  | ❌       | The number of results returned in the response                                                                                                                                                                                                                               |
| preorder          | boolean | ❌       | When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status                                                                                                                           |
| fromPublishDate   | string  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| toPublishDate     | string  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| fromReleaseDate   | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                              |
| toReleaseDate     | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                              |
| genreId           | string  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                      |
| genreName         | string  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/ |
| releaseNameWeight | number  | ❌       |                                                                                                                                                                                                                                                                              |
| labelNameWeight   | number  | ❌       | This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name                                                                                                   |

**Return Type**

`ReleasesResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.releasesSearchSearchV1ReleasesGet({
    q: 'q',
    count: 20,
    preorder: true,
    fromPublishDate: 'from_publish_date',
    toPublishDate: 'to_publish_date',
    fromReleaseDate: 'from_release_date',
    toReleaseDate: 'to_release_date',
    genreId: 'genre_id',
    genreName: 'genre_name',
    releaseNameWeight: 1,
    labelNameWeight: 1,
  });

  console.log(data);
})();
```

## artistsSearchSearchV1ArtistsGet

Returns a set of artist results

- HTTP Method: `GET`
- Endpoint: `/search/v1/artists`

**Parameters**

| Name    | Type   | Required | Description                                                                                                                                                                                                                             |
| :------ | :----- | :------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q       | string | ✅       | Search query text                                                                                                                                                                                                                       |
| count   | number | ❌       | The number of results returned in the response                                                                                                                                                                                          |
| genreId | string | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/ |

**Return Type**

`ArtistsResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.artistsSearchSearchV1ArtistsGet({
    q: 'q',
    count: 20,
    genreId: 'genre_id',
  });

  console.log(data);
})();
```

## labelsSearchSearchV1LabelsGet

Returns a set of label results

- HTTP Method: `GET`
- Endpoint: `/search/v1/labels`

**Parameters**

| Name  | Type   | Required | Description                                    |
| :---- | :----- | :------- | :--------------------------------------------- |
| q     | string | ✅       | Search query text                              |
| count | number | ❌       | The number of results returned in the response |

**Return Type**

`LabelsResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.labelsSearchSearchV1LabelsGet({
    q: 'q',
    count: 20,
  });

  console.log(data);
})();
```

## chartsSearchSearchV1ChartsGet

Returns a set of chart results

- HTTP Method: `GET`
- Endpoint: `/search/v1/charts`

**Parameters**

| Name            | Type    | Required | Description                                                                                                                                                                                                                                                                  |
| :-------------- | :------ | :------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q               | string  | ✅       | Search query text                                                                                                                                                                                                                                                            |
| count           | number  | ❌       | The number of results returned in the response                                                                                                                                                                                                                               |
| genreId         | string  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                      |
| genreName       | string  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/ |
| isApproved      | boolean | ❌       | When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE                                                                                                      |
| fromPublishDate | string  | ❌       | The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| toPublishDate   | string  | ❌       | The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |

**Return Type**

`ChartsResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.chartsSearchSearchV1ChartsGet({
    q: 'q',
    count: 20,
    genreId: 'genre_id',
    genreName: 'genre_name',
    isApproved: true,
    fromPublishDate: 'from_publish_date',
    toPublishDate: 'to_publish_date',
  });

  console.log(data);
})();
```

## allSearchSearchV1AllGet

Returns a set of results for all search types

- HTTP Method: `GET`
- Endpoint: `/search/v1/all`

**Parameters**

| Name                    | Type    | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                               |
| :---------------------- | :------ | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| q                       | string  | ✅       | Search query text                                                                                                                                                                                                                                                                                                                                                                                                         |
| count                   | number  | ❌       | The number of results returned in the response                                                                                                                                                                                                                                                                                                                                                                            |
| preorder                | boolean | ❌       | When FALSE, the response will not include tracks or releases in a pre-order status. When TRUE, the response will include tracks and releases that are in a pre-order status                                                                                                                                                                                                                                               |
| tracksFromReleaseDate   | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| tracksToReleaseDate     | string  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| releasesFromReleaseDate | string  | ❌       | The date a release was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                         |
| releasesToReleaseDate   | string  | ❌       | The date a release was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                         |
| isApproved              | boolean | ❌       | When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE                                                                                                                                                                                                                                                   |
| isAvailableForStreaming | boolean | ❌       | By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming. |

**Return Type**

`MultisearchResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.searchEndpoints.allSearchSearchV1AllGet({
    q: 'q',
    count: 20,
    preorder: true,
    tracksFromReleaseDate: 'tracks_from_release_date',
    tracksToReleaseDate: 'tracks_to_release_date',
    releasesFromReleaseDate: 'releases_from_release_date',
    releasesToReleaseDate: 'releases_to_release_date',
    isApproved: true,
    isAvailableForStreaming: true,
  });

  console.log(data);
})();
```
