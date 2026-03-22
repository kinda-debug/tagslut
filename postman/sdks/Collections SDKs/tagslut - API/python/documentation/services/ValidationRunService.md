# ValidationRunService

A list of all methods in the `ValidationRunService` service. Click on the method name to view detailed information about that method.

| Methods                                                               | Description |
| :-------------------------------------------------------------------- | :---------- |
| [v_6a_resolve_tidal_album_to_isrc](#v_6a_resolve_tidal_album_to_isrc) |             |
| [v_6b_track_by_id_validation](#v_6b_track_by_id_validation)           |             |
| [v_6c_run_notes](#v_6c_run_notes)                                     |             |

## v_6a_resolve_tidal_album_to_isrc

- HTTP Method: `GET`
- Endpoint: `/v1/albums/507881809/tracks`

**Parameters**

| Name         | Type | Required | Description |
| :----------- | :--- | :------- | :---------- |
| country_code | str  | ❌       |             |

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

result = sdk.validation_run.v_6a_resolve_tidal_album_to_isrc(country_code="US")

print(result)
```

## v_6b_track_by_id_validation

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

## v_6c_run_notes

- HTTP Method: `GET`
- Endpoint: `/`

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

result = sdk.validation_run.v_6c_run_notes()

print(result)
```
