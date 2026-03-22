# SearchEndpointsService

A list of all methods in the `SearchEndpointsService` service. Click on the method name to view detailed information about that method.

| Methods                                                                           | Description                                   |
| :-------------------------------------------------------------------------------- | :-------------------------------------------- |
| [tracks_search_search_v1_tracks_get](#tracks_search_search_v1_tracks_get)         | Returns a set of track results                |
| [releases_search_search_v1_releases_get](#releases_search_search_v1_releases_get) | Returns a set of release results              |
| [artists_search_search_v1_artists_get](#artists_search_search_v1_artists_get)     | Returns a set of artist results               |
| [labels_search_search_v1_labels_get](#labels_search_search_v1_labels_get)         | Returns a set of label results                |
| [charts_search_search_v1_charts_get](#charts_search_search_v1_charts_get)         | Returns a set of chart results                |
| [all_search_search_v1_all_get](#all_search_search_v1_all_get)                     | Returns a set of results for all search types |

## tracks_search_search_v1_tracks_get

Returns a set of track results

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name                       | Type | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                               |
| :------------------------- | :--- | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| q                          | str  | ✅       | Search query text                                                                                                                                                                                                                                                                                                                                                                                                         |
| count                      | int  | ❌       | The number of results returned in the response                                                                                                                                                                                                                                                                                                                                                                            |
| preorder                   | bool | ❌       | When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status                                                                                                                                                                                                                                                                        |
| from_publish_date          | str  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                      |
| to_publish_date            | str  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                      |
| from_release_date          | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| to_release_date            | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| genre_id                   | str  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                                                                                                                                                                   |
| genre_name                 | str  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/                                                                                                                                              |
| mix_name                   | str  | ❌       | Search for a specific mix name, ex: original                                                                                                                                                                                                                                                                                                                                                                              |
| from_bpm                   | int  | ❌       |                                                                                                                                                                                                                                                                                                                                                                                                                           |
| to_bpm                     | int  | ❌       |                                                                                                                                                                                                                                                                                                                                                                                                                           |
| key_name                   | str  | ❌       | Search for a specific key in the following format: A Major, A Minor, A# Major, A# Minor, Ab Major, Ab Minor                                                                                                                                                                                                                                                                                                               |
| mix_name_weight            | int  | ❌       | This parameter determines how much weight to put on mix_name using the search query text from q. The higher the value the more weight is put on matching q to mix_name                                                                                                                                                                                                                                                    |
| label_name_weight          | int  | ❌       | This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name                                                                                                                                                                                                                                                |
| dj_edits                   | bool | ❌       | When FALSE, the response will exclude DJ Edit tracks. When TRUE, the response will return only DJ Edit tracks.                                                                                                                                                                                                                                                                                                            |
| ugc_remixes                | bool | ❌       | When FALSE, the response will exclude UGC Remix tracks. When TRUE, the response will return only UGC Remix tracks.                                                                                                                                                                                                                                                                                                        |
| dj_edits_and_ugc_remixes   | bool | ❌       | When FALSE, the response will exclude DJ Edits and UGC Remix tracks. When TRUE, the response will return only DJ Edits or UGC Remix tracks. When parameter is not included, the response will include DJ edits and UGC remixes amongst other tracks.                                                                                                                                                                      |
| is_available_for_streaming | bool | ❌       | By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming. |

**Return Type**

`TracksResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.tracks_search_search_v1_tracks_get(
    q="q",
    count=20,
    preorder=True,
    from_publish_date="from_publish_date",
    to_publish_date="to_publish_date",
    from_release_date="from_release_date",
    to_release_date="to_release_date",
    genre_id="genre_id",
    genre_name="genre_name",
    mix_name="mix_name",
    from_bpm=2,
    to_bpm=9,
    key_name="key_name",
    mix_name_weight=1,
    label_name_weight=1,
    dj_edits=True,
    ugc_remixes=False,
    dj_edits_and_ugc_remixes=False,
    is_available_for_streaming=True
)

print(result)
```

## releases_search_search_v1_releases_get

Returns a set of release results

- HTTP Method: `GET`
- Endpoint: `/search/v1/releases`

**Parameters**

| Name                | Type | Required | Description                                                                                                                                                                                                                                                                  |
| :------------------ | :--- | :------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q                   | str  | ✅       | Search query text                                                                                                                                                                                                                                                            |
| count               | int  | ❌       | The number of results returned in the response                                                                                                                                                                                                                               |
| preorder            | bool | ❌       | When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status                                                                                                                           |
| from_publish_date   | str  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| to_publish_date     | str  | ❌       | The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| from_release_date   | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                              |
| to_release_date     | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                              |
| genre_id            | str  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                      |
| genre_name          | str  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/ |
| release_name_weight | int  | ❌       |                                                                                                                                                                                                                                                                              |
| label_name_weight   | int  | ❌       | This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name                                                                                                   |

**Return Type**

`ReleasesResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.releases_search_search_v1_releases_get(
    q="q",
    count=20,
    preorder=False,
    from_publish_date="from_publish_date",
    to_publish_date="to_publish_date",
    from_release_date="from_release_date",
    to_release_date="to_release_date",
    genre_id="genre_id",
    genre_name="genre_name",
    release_name_weight=1,
    label_name_weight=1
)

print(result)
```

## artists_search_search_v1_artists_get

Returns a set of artist results

- HTTP Method: `GET`
- Endpoint: `/search/v1/artists`

**Parameters**

| Name     | Type | Required | Description                                                                                                                                                                                                                             |
| :------- | :--- | :------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q        | str  | ✅       | Search query text                                                                                                                                                                                                                       |
| count    | int  | ❌       | The number of results returned in the response                                                                                                                                                                                          |
| genre_id | str  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/ |

**Return Type**

`ArtistsResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.artists_search_search_v1_artists_get(
    q="q",
    count=20,
    genre_id="genre_id"
)

print(result)
```

## labels_search_search_v1_labels_get

Returns a set of label results

- HTTP Method: `GET`
- Endpoint: `/search/v1/labels`

**Parameters**

| Name  | Type | Required | Description                                    |
| :---- | :--- | :------- | :--------------------------------------------- |
| q     | str  | ✅       | Search query text                              |
| count | int  | ❌       | The number of results returned in the response |

**Return Type**

`LabelsResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.labels_search_search_v1_labels_get(
    q="q",
    count=20
)

print(result)
```

## charts_search_search_v1_charts_get

Returns a set of chart results

- HTTP Method: `GET`
- Endpoint: `/search/v1/charts`

**Parameters**

| Name              | Type | Required | Description                                                                                                                                                                                                                                                                  |
| :---------------- | :--- | :------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| q                 | str  | ✅       | Search query text                                                                                                                                                                                                                                                            |
| count             | int  | ❌       | The number of results returned in the response                                                                                                                                                                                                                               |
| genre_id          | str  | ❌       | Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/                                      |
| genre_name        | str  | ❌       | Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/ |
| is_approved       | bool | ❌       | When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE                                                                                                      |
| from_publish_date | str  | ❌       | The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |
| to_publish_date   | str  | ❌       | The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD                                                                                                                                                                                         |

**Return Type**

`ChartsResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.charts_search_search_v1_charts_get(
    q="q",
    count=20,
    genre_id="genre_id",
    genre_name="genre_name",
    is_approved=False,
    from_publish_date="from_publish_date",
    to_publish_date="to_publish_date"
)

print(result)
```

## all_search_search_v1_all_get

Returns a set of results for all search types

- HTTP Method: `GET`
- Endpoint: `/search/v1/all`

**Parameters**

| Name                       | Type | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                               |
| :------------------------- | :--- | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| q                          | str  | ✅       | Search query text                                                                                                                                                                                                                                                                                                                                                                                                         |
| count                      | int  | ❌       | The number of results returned in the response                                                                                                                                                                                                                                                                                                                                                                            |
| preorder                   | bool | ❌       | When FALSE, the response will not include tracks or releases in a pre-order status. When TRUE, the response will include tracks and releases that are in a pre-order status                                                                                                                                                                                                                                               |
| tracks_from_release_date   | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| tracks_to_release_date     | str  | ❌       | The date a track was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                           |
| releases_from_release_date | str  | ❌       | The date a release was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                         |
| releases_to_release_date   | str  | ❌       | The date a release was released to the public. Format: YYYY-MM-DD                                                                                                                                                                                                                                                                                                                                                         |
| is_approved                | bool | ❌       | When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE                                                                                                                                                                                                                                                   |
| is_available_for_streaming | bool | ❌       | By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming. |

**Return Type**

`MultisearchResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.search_endpoints.all_search_search_v1_all_get(
    q="q",
    count=20,
    preorder=True,
    tracks_from_release_date="tracks_from_release_date",
    tracks_to_release_date="tracks_to_release_date",
    releases_from_release_date="releases_from_release_date",
    releases_to_release_date="releases_to_release_date",
    is_approved=True,
    is_available_for_streaming=False
)

print(result)
```
