package com.searchservicesdk.models;

import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;

/**
 * Response model for the `all-search` endpoint.
 */
@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class MultisearchResponse {

  /**
   * Response model for the `tracks` endpoint.
   */
  @NonNull
  private TracksResponse tracks;

  @NonNull
  private ArtistsResponse artists;

  @NonNull
  private ChartsResponse charts;

  @NonNull
  private LabelsResponse labels;

  /**
   * Response model for the `releases` endpoint.
   */
  @NonNull
  private ReleasesResponse releases;
}
