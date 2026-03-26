# SearchService

A list of all methods in the `SearchService` service. Click on the method name to view detailed information about that method.

| Methods                                   | Description |
| :---------------------------------------- | :---------- |
| [searchTracksByText](#searchtracksbytext) |             |

## searchTracksByText

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name              | Type                                                                      | Required | Description               |
| :---------------- | :------------------------------------------------------------------------ | :------- | :------------------------ |
| requestParameters | [SearchTracksByTextParameters](../models/SearchTracksByTextParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models.SearchTracksByTextParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    SearchTracksByTextParameters requestParameters = SearchTracksByTextParameters.builder()
      .q("{{beatport_search_query}}")
      .count("10")
      .build();

    Object response = tagslutApiSdk.search.searchTracksByText(requestParameters);

    System.out.println(response);
  }
}

```
