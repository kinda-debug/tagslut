# ValidationRunService

A list of all methods in the `ValidationRunService` service. Click on the method name to view detailed information about that method.

| Methods                                                    | Description |
| :--------------------------------------------------------- | :---------- |
| [\_6aResolveTidalAlbumToIsrc](#_6aresolvetidalalbumtoisrc) |             |
| [_6bTrackByIdValidation_](#_6btrackbyidvalidation_)        |             |
| [\_6cRunNotes](#_6crunnotes)                               |             |

## \_6aResolveTidalAlbumToIsrc

- HTTP Method: `GET`
- Endpoint: `/v1/albums/507881809/tracks`

**Parameters**

| Name        | Type   | Required | Description |
| :---------- | :----- | :------- | :---------- |
| countryCode | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.validationRun._6aResolveTidalAlbumToIsrc({
    countryCode: 'US',
  });

  console.log(data);
})();
```

## _6bTrackByIdValidation_

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

## \_6cRunNotes

- HTTP Method: `GET`
- Endpoint: `/`

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.validationRun._6cRunNotes();

  console.log(data);
})();
```
