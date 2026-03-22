package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
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
public class TracksSearchSearchV1TracksGetParameters {

  /**
   * Search query text
   */
  @NonNull
  private String q;

  /**
   * The number of results returned in the response
   */
  @JsonProperty("count")
  private JsonNullable<Long> count;

  /**
   *
   * When FALSE, the response will not include tracks in a pre-order status.
   *
   * When TRUE, the response will include tracks that are in a pre-order status
   *
   */
  @JsonProperty("preorder")
  private JsonNullable<Boolean> preorder;

  /**
   *
   * The date a track was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("from_publish_date")
  private JsonNullable<String> fromPublishDate;

  /**
   *
   * The date a track was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("to_publish_date")
  private JsonNullable<String> toPublishDate;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("from_release_date")
  private JsonNullable<String> fromReleaseDate;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("to_release_date")
  private JsonNullable<String> toReleaseDate;

  /**
   *
   * Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
   * by separating them with a comma, ex: (89, 6, 14).
   *
   * For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/
   *
   */
  @JsonProperty("genre_id")
  private JsonNullable<String> genreId;

  /**
   *
   * Returns tracks that have a genre which partially matches the value inputed.
   *
   * For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc.
   *
   * For a list of genres and their names, make a GET call to our API route /catalog/genres/
   *
   */
  @JsonProperty("genre_name")
  private JsonNullable<String> genreName;

  /**
   * Search for a specific mix name, ex: original
   */
  @JsonProperty("mix_name")
  private JsonNullable<String> mixName;

  @JsonProperty("from_bpm")
  private JsonNullable<Long> fromBpm;

  @JsonProperty("to_bpm")
  private JsonNullable<Long> toBpm;

  /**
   *
   * Search for a specific key in the following format:
   *
   * A Major, A Minor, A# Major, A# Minor, Ab Major, Ab Minor
   *
   */
  @JsonProperty("key_name")
  private JsonNullable<String> keyName;

  /**
   *
   * This parameter determines how much weight to put on mix_name using the search query text from q.
   *
   * The higher the value the more weight is put on matching q to mix_name
   *
   */
  @JsonProperty("mix_name_weight")
  private JsonNullable<Long> mixNameWeight;

  /**
   *
   * This parameter determines how much weight to put on label_name using the search query text from q.
   *
   * The higher the value the more weight is put on matching q to label_name
   *
   */
  @JsonProperty("label_name_weight")
  private JsonNullable<Long> labelNameWeight;

  /**
   *
   * When FALSE, the response will exclude DJ Edit tracks.
   *
   * When TRUE, the response will return only DJ Edit tracks.
   *
   */
  @JsonProperty("dj_edits")
  private JsonNullable<Boolean> djEdits;

  /**
   *
   * When FALSE, the response will exclude UGC Remix tracks.
   *
   * When TRUE, the response will return only UGC Remix tracks.
   *
   */
  @JsonProperty("ugc_remixes")
  private JsonNullable<Boolean> ugcRemixes;

  /**
   *
   * When FALSE, the response will exclude DJ Edits and UGC Remix tracks.
   *
   * When TRUE, the response will return only DJ Edits or UGC Remix tracks.
   *
   * When parameter is not included, the response will include DJ edits and UGC remixes amongst other tracks.
   *
   */
  @JsonProperty("dj_edits_and_ugc_remixes")
  private JsonNullable<Boolean> djEditsAndUgcRemixes;

  /**
   *
   * By default the response will return both streamable and non-streamable tracks.
   *
   * **Note**: This is dependent on your app scope, if your scope inherently does not allow
   * non-streamable tracks then only streamable tracks will be returned always.
   *
   * When FALSE, the response will return only tracks that are not available for streaming.
   *
   * When TRUE, the response will return only tracks that are available for streaming.
   *
   */
  @JsonProperty("is_available_for_streaming")
  private JsonNullable<Boolean> isAvailableForStreaming;

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  @JsonIgnore
  public Boolean getPreorder() {
    return preorder.orElse(null);
  }

  @JsonIgnore
  public String getFromPublishDate() {
    return fromPublishDate.orElse(null);
  }

  @JsonIgnore
  public String getToPublishDate() {
    return toPublishDate.orElse(null);
  }

  @JsonIgnore
  public String getFromReleaseDate() {
    return fromReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getToReleaseDate() {
    return toReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getGenreId() {
    return genreId.orElse(null);
  }

  @JsonIgnore
  public String getGenreName() {
    return genreName.orElse(null);
  }

  @JsonIgnore
  public String getMixName() {
    return mixName.orElse(null);
  }

  @JsonIgnore
  public Long getFromBpm() {
    return fromBpm.orElse(null);
  }

  @JsonIgnore
  public Long getToBpm() {
    return toBpm.orElse(null);
  }

  @JsonIgnore
  public String getKeyName() {
    return keyName.orElse(null);
  }

  @JsonIgnore
  public Long getMixNameWeight() {
    return mixNameWeight.orElse(null);
  }

  @JsonIgnore
  public Long getLabelNameWeight() {
    return labelNameWeight.orElse(null);
  }

  @JsonIgnore
  public Boolean getDjEdits() {
    return djEdits.orElse(null);
  }

  @JsonIgnore
  public Boolean getUgcRemixes() {
    return ugcRemixes.orElse(null);
  }

  @JsonIgnore
  public Boolean getDjEditsAndUgcRemixes() {
    return djEditsAndUgcRemixes.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsAvailableForStreaming() {
    return isAvailableForStreaming.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class TracksSearchSearchV1TracksGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public TracksSearchSearchV1TracksGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> preorder = JsonNullable.undefined();

    @JsonProperty("preorder")
    public TracksSearchSearchV1TracksGetParametersBuilder preorder(Boolean value) {
      if (value == null) {
        throw new IllegalStateException("preorder cannot be null");
      }
      this.preorder = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> fromPublishDate = JsonNullable.undefined();

    @JsonProperty("from_publish_date")
    public TracksSearchSearchV1TracksGetParametersBuilder fromPublishDate(String value) {
      this.fromPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> toPublishDate = JsonNullable.undefined();

    @JsonProperty("to_publish_date")
    public TracksSearchSearchV1TracksGetParametersBuilder toPublishDate(String value) {
      this.toPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> fromReleaseDate = JsonNullable.undefined();

    @JsonProperty("from_release_date")
    public TracksSearchSearchV1TracksGetParametersBuilder fromReleaseDate(String value) {
      this.fromReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> toReleaseDate = JsonNullable.undefined();

    @JsonProperty("to_release_date")
    public TracksSearchSearchV1TracksGetParametersBuilder toReleaseDate(String value) {
      this.toReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreId = JsonNullable.undefined();

    @JsonProperty("genre_id")
    public TracksSearchSearchV1TracksGetParametersBuilder genreId(String value) {
      this.genreId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreName = JsonNullable.undefined();

    @JsonProperty("genre_name")
    public TracksSearchSearchV1TracksGetParametersBuilder genreName(String value) {
      this.genreName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> mixName = JsonNullable.undefined();

    @JsonProperty("mix_name")
    public TracksSearchSearchV1TracksGetParametersBuilder mixName(String value) {
      this.mixName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> fromBpm = JsonNullable.undefined();

    @JsonProperty("from_bpm")
    public TracksSearchSearchV1TracksGetParametersBuilder fromBpm(Long value) {
      this.fromBpm = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> toBpm = JsonNullable.undefined();

    @JsonProperty("to_bpm")
    public TracksSearchSearchV1TracksGetParametersBuilder toBpm(Long value) {
      this.toBpm = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> keyName = JsonNullable.undefined();

    @JsonProperty("key_name")
    public TracksSearchSearchV1TracksGetParametersBuilder keyName(String value) {
      this.keyName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> mixNameWeight = JsonNullable.of(1L);

    @JsonProperty("mix_name_weight")
    public TracksSearchSearchV1TracksGetParametersBuilder mixNameWeight(Long value) {
      if (value == null) {
        throw new IllegalStateException("mixNameWeight cannot be null");
      }
      this.mixNameWeight = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> labelNameWeight = JsonNullable.of(1L);

    @JsonProperty("label_name_weight")
    public TracksSearchSearchV1TracksGetParametersBuilder labelNameWeight(Long value) {
      if (value == null) {
        throw new IllegalStateException("labelNameWeight cannot be null");
      }
      this.labelNameWeight = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> djEdits = JsonNullable.undefined();

    @JsonProperty("dj_edits")
    public TracksSearchSearchV1TracksGetParametersBuilder djEdits(Boolean value) {
      this.djEdits = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> ugcRemixes = JsonNullable.undefined();

    @JsonProperty("ugc_remixes")
    public TracksSearchSearchV1TracksGetParametersBuilder ugcRemixes(Boolean value) {
      this.ugcRemixes = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> djEditsAndUgcRemixes = JsonNullable.undefined();

    @JsonProperty("dj_edits_and_ugc_remixes")
    public TracksSearchSearchV1TracksGetParametersBuilder djEditsAndUgcRemixes(Boolean value) {
      this.djEditsAndUgcRemixes = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isAvailableForStreaming = JsonNullable.undefined();

    @JsonProperty("is_available_for_streaming")
    public TracksSearchSearchV1TracksGetParametersBuilder isAvailableForStreaming(Boolean value) {
      this.isAvailableForStreaming = JsonNullable.of(value);
      return this;
    }
  }
}
