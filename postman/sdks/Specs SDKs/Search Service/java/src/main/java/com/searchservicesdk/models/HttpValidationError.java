package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;
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
@NoArgsConstructor
@AllArgsConstructor
public class HttpValidationError {

  @JsonProperty("detail")
  private JsonNullable<List<ValidationError>> detail;

  @JsonIgnore
  public List<ValidationError> getDetail() {
    return detail.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class HttpValidationErrorBuilder {

    private JsonNullable<List<ValidationError>> detail = JsonNullable.undefined();

    @JsonProperty("detail")
    public HttpValidationErrorBuilder detail(List<ValidationError> value) {
      if (value == null) {
        throw new IllegalStateException("detail cannot be null");
      }
      this.detail = JsonNullable.of(value);
      return this;
    }
  }
}
