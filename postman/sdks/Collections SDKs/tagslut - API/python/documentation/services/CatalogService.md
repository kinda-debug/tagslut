# CatalogService

A list of all methods in the `CatalogService` service. Click on the method name to view detailed information about that method.

| Methods                                                                         | Description |
| :------------------------------------------------------------------------------ | :---------- |
| [track_by_id](#track_by_id)                                                     |             |
| [tracks_by_isrc_query_param](#tracks_by_isrc_query_param)                       |             |
| [isrc_store_lookup_path_based_phase_3d](#isrc_store_lookup_path_based_phase_3d) |             |
| [release_by_id](#release_by_id)                                                 |             |
| [release_tracks](#release_tracks)                                               |             |

## track_by_id

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/{beatport_test_track_id}`

**Parameters**

| Name                   | Type | Required | Description |
| :--------------------- | :--- | :------- | :---------- |
| beatport_test_track_id | str  | ✅       |             |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

result = sdk.catalog.track_by_id(beatport_test_track_id="beatport_test_track_id")

print(result)
```

## tracks_by_isrc_query_param

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks`

**Parameters**

| Name | Type | Required | Description |
| :--- | :--- | :------- | :---------- |
| isrc | str  | ❌       |             |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

result = sdk.catalog.tracks_by_isrc_query_param(isrc="{{beatport_test_isrc}}")

print(result)
```

## isrc_store_lookup_path_based_phase_3d

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/store/{beatport_test_isrc}`

**Parameters**

| Name               | Type | Required | Description |
| :----------------- | :--- | :------- | :---------- |
| beatport_test_isrc | str  | ✅       |             |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

result = sdk.catalog.isrc_store_lookup_path_based_phase_3d(beatport_test_isrc="beatport_test_isrc")

print(result)
```

## release_by_id

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}`

**Parameters**

| Name                     | Type | Required | Description |
| :----------------------- | :--- | :------- | :---------- |
| beatport_test_release_id | str  | ✅       |             |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

result = sdk.catalog.release_by_id(beatport_test_release_id="beatport_test_release_id")

print(result)
```

## release_tracks

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}/tracks`

**Parameters**

| Name                     | Type | Required | Description |
| :----------------------- | :--- | :------- | :---------- |
| beatport_test_release_id | str  | ✅       |             |
| per_page                 | str  | ❌       |             |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

result = sdk.catalog.release_tracks(
    beatport_test_release_id="beatport_test_release_id",
    per_page="100"
)

print(result)
```
