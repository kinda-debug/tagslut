# MyLibraryService

A list of all methods in the `MyLibraryService` service. Click on the method name to view detailed information about that method.

| Methods                                   | Description |
| :---------------------------------------- | :---------- |
| [my_beatport_tracks](#my_beatport_tracks) |             |
| [my_account](#my_account)                 |             |

## my_beatport_tracks

- HTTP Method: `GET`
- Endpoint: `/v4/my/beatport/tracks`

**Parameters**

| Name     | Type | Required | Description |
| :------- | :--- | :------- | :---------- |
| page     | str  | ❌       |             |
| per_page | str  | ❌       |             |

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

result = sdk.my_library.my_beatport_tracks(
    page="1",
    per_page="25"
)

print(result)
```

## my_account

- HTTP Method: `GET`
- Endpoint: `/v4/my/account`

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

result = sdk.my_library.my_account()

print(result)
```
