package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;

/**
 * Response model for the `health-check` endpoint.
 */
@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class HealthCheckResponse {

  /**
   * The origin of the request.
   */
  @NonNull
  @JsonProperty("remote_addr")
  private String remoteAddr;

  /**
   * The current docker image used by the service.
   */
  @NonNull
  @JsonProperty("commit_hash")
  private String commitHash;

  /**
   * Bool that indicates if the service is connected to elasticsearch or not.
   */
  @NonNull
  @JsonProperty("service_es_connected")
  private Boolean serviceEsConnected;
}
