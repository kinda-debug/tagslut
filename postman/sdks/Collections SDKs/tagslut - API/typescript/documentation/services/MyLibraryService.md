# MyLibraryService

A list of all methods in the `MyLibraryService` service. Click on the method name to view detailed information about that method.

| Methods                               | Description |
| :------------------------------------ | :---------- |
| [myBeatportTracks](#mybeatporttracks) |             |
| [myAccount](#myaccount)               |             |

## myBeatportTracks

- HTTP Method: `GET`
- Endpoint: `/v4/my/beatport/tracks`

**Parameters**

| Name    | Type   | Required | Description |
| :------ | :----- | :------- | :---------- |
| page    | string | ❌       |             |
| perPage | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.myLibrary.myBeatportTracks({
    page: '1',
    perPage: '25',
  });

  console.log(data);
})();
```

## myAccount

- HTTP Method: `GET`
- Endpoint: `/v4/my/account`

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.myLibrary.myAccount();

  console.log(data);
})();
```
