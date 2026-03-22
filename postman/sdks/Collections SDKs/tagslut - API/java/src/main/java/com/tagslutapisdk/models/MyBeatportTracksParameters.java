package com.tagslutapisdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
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
public class MyBeatportTracksParameters {

  @JsonProperty("page")
  private JsonNullable<String> page;

  @JsonProperty("per_page")
  private JsonNullable<String> perPage;

  @JsonIgnore
  public String getPage() {
    return page.orElse(null);
  }

  @JsonIgnore
  public String getPerPage() {
    return perPage.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class MyBeatportTracksParametersBuilder {

    private JsonNullable<String> page = JsonNullable.undefined();

    @JsonProperty("page")
    public MyBeatportTracksParametersBuilder page(String value) {
      this.page = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> perPage = JsonNullable.undefined();

    @JsonProperty("per_page")
    public MyBeatportTracksParametersBuilder perPage(String value) {
      this.perPage = JsonNullable.of(value);
      return this;
    }
  }
}
