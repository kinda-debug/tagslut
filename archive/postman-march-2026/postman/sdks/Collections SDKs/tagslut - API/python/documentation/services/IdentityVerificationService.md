# IdentityVerificationService

A list of all methods in the `IdentityVerificationService` service. Click on the method name to view detailed information about that method.

| Methods                                                         | Description |
| :-------------------------------------------------------------- | :---------- |
| [v_5a_beatport_isrc_lookup](#v_5a_beatport_isrc_lookup)         |             |
| [v_5b_tidal_isrc_cross_check](#v_5b_tidal_isrc_cross_check)     |             |
| [v_5c_spotify_isrc_cross_check](#v_5c_spotify_isrc_cross_check) |             |

## v_5a_beatport_isrc_lookup

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

## v_5b_tidal_isrc_cross_check

- HTTP Method: `GET`
- Endpoint: `/v1/tracks`

**Parameters**

| Name         | Type | Required | Description |
| :----------- | :--- | :------- | :---------- |
| isrc         | str  | ❌       |             |
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

result = sdk.identity_verification.v_5b_tidal_isrc_cross_check(
    isrc="{{beatport_verified_isrc}}",
    country_code="US"
)

print(result)
```

## v_5c_spotify_isrc_cross_check

- HTTP Method: `GET`
- Endpoint: `/v1/search`

**Parameters**

| Name   | Type | Required | Description |
| :----- | :--- | :------- | :---------- |
| q      | str  | ❌       |             |
| type\_ | str  | ❌       |             |

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

result = sdk.identity_verification.v_5c_spotify_isrc_cross_check(
    q="isrc:{{beatport_verified_isrc}}",
    type_="track"
)

print(result)
```
