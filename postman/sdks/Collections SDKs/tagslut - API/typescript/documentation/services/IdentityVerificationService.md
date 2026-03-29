# IdentityVerificationService

A list of all methods in the `IdentityVerificationService` service. Click on the method name to view detailed information about that method.

| Methods                                                | Description |
| :----------------------------------------------------- | :---------- |
| [\_5aBeatportIsrcLookup](#_5abeatportisrclookup)       |             |
| [\_5bTidalIsrcCrossCheck](#_5btidalisrccrosscheck)     |             |
| [\_5cSpotifyIsrcCrossCheck](#_5cspotifyisrccrosscheck) |             |

## \_5aBeatportIsrcLookup

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks`

**Parameters**

| Name | Type   | Required | Description |
| :--- | :----- | :------- | :---------- |
| isrc | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.catalog.tracksByIsrcQueryParam_({
    isrc: '{{beatport_test_isrc}}',
  });

  console.log(data);
})();
```

## \_5bTidalIsrcCrossCheck

- HTTP Method: `GET`
- Endpoint: `/v1/tracks`

**Parameters**

| Name        | Type   | Required | Description |
| :---------- | :----- | :------- | :---------- |
| isrc        | string | ❌       |             |
| countryCode | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.identityVerification._5bTidalIsrcCrossCheck({
    isrc: '{{beatport_verified_isrc}}',
    countryCode: 'US',
  });

  console.log(data);
})();
```

## \_5cSpotifyIsrcCrossCheck

- HTTP Method: `GET`
- Endpoint: `/v1/search`

**Parameters**

| Name | Type   | Required | Description |
| :--- | :----- | :------- | :---------- |
| q    | string | ❌       |             |
| type | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.identityVerification._5cSpotifyIsrcCrossCheck({
    q: 'isrc:{{beatport_verified_isrc}}',
    type: 'track',
  });

  console.log(data);
})();
```
