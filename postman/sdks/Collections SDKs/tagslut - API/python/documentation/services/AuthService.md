# AuthService

A list of all methods in the `AuthService` service. Click on the method name to view detailed information about that method.

| Methods                                                       | Description |
| :------------------------------------------------------------ | :---------- |
| [get_token_client_credentials](#get_token_client_credentials) |             |
| [introspect_token](#introspect_token)                         |             |

## get_token_client_credentials

- HTTP Method: `POST`
- Endpoint: `/v4/auth/o/token`

**Parameters**

| Name         | Type                                                                              | Required | Description       |
| :----------- | :-------------------------------------------------------------------------------- | :------- | :---------------- |
| request_body | [GetTokenClientCredentialsRequest](../models/GetTokenClientCredentialsRequest.md) | ✅       | The request body. |

**Return Type**

`Any`

**Example Usage Code Snippet**

```python
from tagslut_api_sdk import TagslutApiSdk, Environment
from tagslut_api_sdk.models import GetTokenClientCredentialsRequest

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000
)

request_body = GetTokenClientCredentialsRequest(
    grant_type="client_credentials",
    client_id="{{beatport_client_id}}",
    client_secret="{{beatport_client_secret}}"
)

result = sdk.auth.get_token_client_credentials(request_body=request_body)

print(result)
```

## introspect_token

- HTTP Method: `GET`
- Endpoint: `/v4/auth/o/introspect`

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

result = sdk.auth.introspect_token()

print(result)
```
