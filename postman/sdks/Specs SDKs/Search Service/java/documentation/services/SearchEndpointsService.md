# SearchEndpointsService

A list of all methods in the `SearchEndpointsService` service. Click on the method name to view detailed information about that method.

| Methods                                                                 | Description                                   |
| :---------------------------------------------------------------------- | :-------------------------------------------- |
| [tracksSearchSearchV1TracksGet](#trackssearchsearchv1tracksget)         | Returns a set of track results                |
| [releasesSearchSearchV1ReleasesGet](#releasessearchsearchv1releasesget) | Returns a set of release results              |
| [artistsSearchSearchV1ArtistsGet](#artistssearchsearchv1artistsget)     | Returns a set of artist results               |
| [labelsSearchSearchV1LabelsGet](#labelssearchsearchv1labelsget)         | Returns a set of label results                |
| [chartsSearchSearchV1ChartsGet](#chartssearchsearchv1chartsget)         | Returns a set of chart results                |
| [allSearchSearchV1AllGet](#allsearchsearchv1allget)                     | Returns a set of results for all search types |

## tracksSearchSearchV1TracksGet

Returns a set of track results

- HTTP Method: `GET`
- Endpoint: `/search/v1/tracks`

**Parameters**

| Name              | Type                                                                                            | Required | Description               |
| :---------------- | :---------------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [TracksSearchSearchV1TracksGetParameters](../models/TracksSearchSearchV1TracksGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`TracksResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.TracksResponse;
import com.searchservicesdk.models.TracksSearchSearchV1TracksGetParameters;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    TracksSearchSearchV1TracksGetParameters requestParameters =
      TracksSearchSearchV1TracksGetParameters.builder()
        .q("q")
        .count(20L)
        .preorder(true)
        .fromPublishDate("from_publish_date")
        .toPublishDate("to_publish_date")
        .fromReleaseDate("from_release_date")
        .toReleaseDate("to_release_date")
        .genreId("genre_id")
        .genreName("genre_name")
        .mixName("mix_name")
        .fromBpm(2L)
        .toBpm(9L)
        .keyName("key_name")
        .mixNameWeight(1L)
        .labelNameWeight(1L)
        .djEdits(true)
        .ugcRemixes(false)
        .djEditsAndUgcRemixes(false)
        .isAvailableForStreaming(true)
        .build();

    TracksResponse response = searchServiceSdk.searchEndpoints.tracksSearchSearchV1TracksGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```

## releasesSearchSearchV1ReleasesGet

Returns a set of release results

- HTTP Method: `GET`
- Endpoint: `/search/v1/releases`

**Parameters**

| Name              | Type                                                                                                    | Required | Description               |
| :---------------- | :------------------------------------------------------------------------------------------------------ | :------- | :------------------------ |
| requestParameters | [ReleasesSearchSearchV1ReleasesGetParameters](../models/ReleasesSearchSearchV1ReleasesGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`ReleasesResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.ReleasesResponse;
import com.searchservicesdk.models.ReleasesSearchSearchV1ReleasesGetParameters;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    ReleasesSearchSearchV1ReleasesGetParameters requestParameters =
      ReleasesSearchSearchV1ReleasesGetParameters.builder()
        .q("q")
        .count(20L)
        .preorder(false)
        .fromPublishDate("from_publish_date")
        .toPublishDate("to_publish_date")
        .fromReleaseDate("from_release_date")
        .toReleaseDate("to_release_date")
        .genreId("genre_id")
        .genreName("genre_name")
        .releaseNameWeight(1L)
        .labelNameWeight(1L)
        .build();

    ReleasesResponse response = searchServiceSdk.searchEndpoints.releasesSearchSearchV1ReleasesGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```

## artistsSearchSearchV1ArtistsGet

Returns a set of artist results

- HTTP Method: `GET`
- Endpoint: `/search/v1/artists`

**Parameters**

| Name              | Type                                                                                                | Required | Description               |
| :---------------- | :-------------------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [ArtistsSearchSearchV1ArtistsGetParameters](../models/ArtistsSearchSearchV1ArtistsGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`ArtistsResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.ArtistsResponse;
import com.searchservicesdk.models.ArtistsSearchSearchV1ArtistsGetParameters;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    ArtistsSearchSearchV1ArtistsGetParameters requestParameters =
      ArtistsSearchSearchV1ArtistsGetParameters.builder()
        .q("q")
        .count(20L)
        .genreId("genre_id")
        .build();

    ArtistsResponse response = searchServiceSdk.searchEndpoints.artistsSearchSearchV1ArtistsGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```

## labelsSearchSearchV1LabelsGet

Returns a set of label results

- HTTP Method: `GET`
- Endpoint: `/search/v1/labels`

**Parameters**

| Name              | Type                                                                                            | Required | Description               |
| :---------------- | :---------------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [LabelsSearchSearchV1LabelsGetParameters](../models/LabelsSearchSearchV1LabelsGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`LabelsResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.LabelsResponse;
import com.searchservicesdk.models.LabelsSearchSearchV1LabelsGetParameters;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    LabelsSearchSearchV1LabelsGetParameters requestParameters =
      LabelsSearchSearchV1LabelsGetParameters.builder().q("q").count(20L).build();

    LabelsResponse response = searchServiceSdk.searchEndpoints.labelsSearchSearchV1LabelsGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```

## chartsSearchSearchV1ChartsGet

Returns a set of chart results

- HTTP Method: `GET`
- Endpoint: `/search/v1/charts`

**Parameters**

| Name              | Type                                                                                            | Required | Description               |
| :---------------- | :---------------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [ChartsSearchSearchV1ChartsGetParameters](../models/ChartsSearchSearchV1ChartsGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`ChartsResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.ChartsResponse;
import com.searchservicesdk.models.ChartsSearchSearchV1ChartsGetParameters;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    ChartsSearchSearchV1ChartsGetParameters requestParameters =
      ChartsSearchSearchV1ChartsGetParameters.builder()
        .q("q")
        .count(20L)
        .genreId("genre_id")
        .genreName("genre_name")
        .isApproved(false)
        .fromPublishDate("from_publish_date")
        .toPublishDate("to_publish_date")
        .build();

    ChartsResponse response = searchServiceSdk.searchEndpoints.chartsSearchSearchV1ChartsGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```

## allSearchSearchV1AllGet

Returns a set of results for all search types

- HTTP Method: `GET`
- Endpoint: `/search/v1/all`

**Parameters**

| Name              | Type                                                                                | Required | Description               |
| :---------------- | :---------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [AllSearchSearchV1AllGetParameters](../models/AllSearchSearchV1AllGetParameters.md) | ✅       | Request Parameters Object |

**Return Type**

`MultisearchResponse`

**Example Usage Code Snippet**

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.AllSearchSearchV1AllGetParameters;
import com.searchservicesdk.models.MultisearchResponse;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    AllSearchSearchV1AllGetParameters requestParameters =
      AllSearchSearchV1AllGetParameters.builder()
        .q("q")
        .count(20L)
        .preorder(true)
        .tracksFromReleaseDate("tracks_from_release_date")
        .tracksToReleaseDate("tracks_to_release_date")
        .releasesFromReleaseDate("releases_from_release_date")
        .releasesToReleaseDate("releases_to_release_date")
        .isApproved(true)
        .isAvailableForStreaming(false)
        .build();

    MultisearchResponse response = searchServiceSdk.searchEndpoints.allSearchSearchV1AllGet(
      requestParameters
    );

    System.out.println(response);
  }
}

```
