package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;
import org.openapitools.jackson.nullable.JsonNullable;

@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class ArtistsDefaultModel {

  @NonNull
  private Double score;

  @NonNull
  private Long enabled;

  @NonNull
  @JsonProperty("available_worldwide")
  private Long availableWorldwide;

  @NonNull
  @JsonProperty("artist_id")
  private Long artistId;

  @NonNull
  @JsonProperty("artist_name")
  private String artistName;

  @JsonProperty("update_date")
  private JsonNullable<String> updateDate;

  @JsonProperty("latest_publish_date")
  private JsonNullable<String> latestPublishDate;

  @JsonProperty("downloads")
  private JsonNullable<Long> downloads;

  @JsonProperty("genre")
  private JsonNullable<List<GenreModel>> genre;

  @JsonProperty("artist_image_uri")
  private JsonNullable<String> artistImageUri;

  @JsonProperty("artist_image_dynamic_uri")
  private JsonNullable<String> artistImageDynamicUri;

  @JsonIgnore
  public String getUpdateDate() {
    return updateDate.orElse(null);
  }

  @JsonIgnore
  public String getLatestPublishDate() {
    return latestPublishDate.orElse(null);
  }

  @JsonIgnore
  public Long getDownloads() {
    return downloads.orElse(null);
  }

  @JsonIgnore
  public List<GenreModel> getGenre() {
    return genre.orElse(null);
  }

  @JsonIgnore
  public String getArtistImageUri() {
    return artistImageUri.orElse(null);
  }

  @JsonIgnore
  public String getArtistImageDynamicUri() {
    return artistImageDynamicUri.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ArtistsDefaultModelBuilder {

    private JsonNullable<String> updateDate = JsonNullable.undefined();

    @JsonProperty("update_date")
    public ArtistsDefaultModelBuilder updateDate(String value) {
      this.updateDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> latestPublishDate = JsonNullable.undefined();

    @JsonProperty("latest_publish_date")
    public ArtistsDefaultModelBuilder latestPublishDate(String value) {
      this.latestPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> downloads = JsonNullable.undefined();

    @JsonProperty("downloads")
    public ArtistsDefaultModelBuilder downloads(Long value) {
      this.downloads = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<List<GenreModel>> genre = JsonNullable.undefined();

    @JsonProperty("genre")
    public ArtistsDefaultModelBuilder genre(List<GenreModel> value) {
      this.genre = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> artistImageUri = JsonNullable.undefined();

    @JsonProperty("artist_image_uri")
    public ArtistsDefaultModelBuilder artistImageUri(String value) {
      this.artistImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> artistImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("artist_image_dynamic_uri")
    public ArtistsDefaultModelBuilder artistImageDynamicUri(String value) {
      this.artistImageDynamicUri = JsonNullable.of(value);
      return this;
    }
  }
}
