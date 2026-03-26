# CatalogService

A list of all methods in the `CatalogService` service. Click on the method name to view detailed information about that method.

| Methods                                                                | Description |
| :--------------------------------------------------------------------- | :---------- |
| [trackById](#trackbyid)                                                |             |
| [tracksByIsrcQueryParam\_](#tracksbyisrcqueryparam_)                   |             |
| [isrcStoreLookupPathBasedPhase3d\_](#isrcstorelookuppathbasedphase3d_) |             |
| [releaseById](#releasebyid)                                            |             |
| [releaseTracks](#releasetracks)                                        |             |

## trackById

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/{beatport_test_track_id}`

**Parameters**

| Name                | Type   | Required | Description |
| :------------------ | :----- | :------- | :---------- |
| beatportTestTrackId | string | ✅       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.catalog.trackById('beatport_test_track_id');

  console.log(data);
})();
```

## tracksByIsrcQueryParam\_

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

## isrcStoreLookupPathBasedPhase3d\_

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/store/{beatport_test_isrc}`

**Parameters**

| Name             | Type   | Required | Description |
| :--------------- | :----- | :------- | :---------- |
| beatportTestIsrc | string | ✅       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.catalog.isrcStoreLookupPathBasedPhase3d_('beatport_test_isrc');

  console.log(data);
})();
```

## releaseById

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}`

**Parameters**

| Name                  | Type   | Required | Description |
| :-------------------- | :----- | :------- | :---------- |
| beatportTestReleaseId | string | ✅       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.catalog.releaseById('beatport_test_release_id');

  console.log(data);
})();
```

## releaseTracks

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}/tracks`

**Parameters**

| Name                  | Type   | Required | Description |
| :-------------------- | :----- | :------- | :---------- |
| beatportTestReleaseId | string | ✅       |             |
| perPage               | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.catalog.releaseTracks('beatport_test_release_id', {
    perPage: '100',
  });

  console.log(data);
})();
```
