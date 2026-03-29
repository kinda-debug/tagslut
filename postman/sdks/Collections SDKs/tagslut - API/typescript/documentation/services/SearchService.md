# SearchService

A list of all methods in the `SearchService` service. Click on the method name to view detailed information about that method.

| Methods                                   | Description |
| :---------------------------------------- | :---------- |
| [searchTracksByText](#searchtracksbytext) |             |

## searchTracksByText

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name  | Type   | Required | Description |
| :---- | :----- | :------- | :---------- |
| q     | string | ❌       |             |
| count | string | ❌       |             |

**Return Type**

`any`

**Example Usage Code Snippet**

```typescript
import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.search.searchTracksByText({
    q: '{{beatport_search_query}}',
    count: '10',
  });

  console.log(data);
})();
```
