# AuthService

A list of all methods in the `AuthService` service. Click on the method name to view detailed information about that method.

| Methods                                                    | Description |
| :--------------------------------------------------------- | :---------- |
| [getTokenClientCredentials\_](#gettokenclientcredentials_) |             |
| [introspectToken](#introspecttoken)                        |             |

## getTokenClientCredentials\_

- HTTP Method: `POST`
- Endpoint: `/v4/auth/o/token`

**Parameters**

| Name | Type                                                                              | Required | Description       |
| :--- | :-------------------------------------------------------------------------------- | :------- | :---------------- |
| body | [GetTokenClientCredentialsRequest](../models/GetTokenClientCredentialsRequest.md) | ✅       | The request body. |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { GetTokenClientCredentialsRequest, TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const getTokenClientCredentialsRequest: GetTokenClientCredentialsRequest = {
    grantType: 'client_credentials',
    clientId: '{{beatport_client_id}}',
    clientSecret: '{{beatport_client_secret}}',
  };

  const data = await tagslutApiSdk.auth.getTokenClientCredentials_(
    getTokenClientCredentialsRequest,
  );

  console.log(data);
})();
```

## introspectToken

- HTTP Method: `GET`
- Endpoint: `/v4/auth/o/introspect`

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.auth.introspectToken();

  console.log(data);
})();
```
