# SearchService

A list of all methods in the `SearchService` service. Click on the method name to view detailed information about that method.

| Methods                                         | Description |
| :---------------------------------------------- | :---------- |
| [search_tracks_by_text](#search_tracks_by_text) |             |

## search_tracks_by_text

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name  | Type | Required | Description |
| :---- | :--- | :------- | :---------- |
| q     | str  | ❌       |             |
| count | str  | ❌       |             |

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

result = sdk.search.search_tracks_by_text(
    q="{{beatport_search_query}}",
    count="10"
)

print(result)
```
