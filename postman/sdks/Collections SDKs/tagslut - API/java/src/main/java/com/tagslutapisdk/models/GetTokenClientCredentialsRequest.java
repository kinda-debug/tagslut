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
public class GetTokenClientCredentialsRequest {

  @JsonProperty("grant_type")
  private JsonNullable<String> grantType;

  @JsonProperty("client_id")
  private JsonNullable<String> clientId;

  @JsonProperty("client_secret")
  private JsonNullable<String> clientSecret;

  @JsonIgnore
  public String getGrantType() {
    return grantType.orElse(null);
  }

  @JsonIgnore
  public String getClientId() {
    return clientId.orElse(null);
  }

  @JsonIgnore
  public String getClientSecret() {
    return clientSecret.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class GetTokenClientCredentialsRequestBuilder {

    private JsonNullable<String> grantType = JsonNullable.undefined();

    @JsonProperty("grant_type")
    public GetTokenClientCredentialsRequestBuilder grantType(String value) {
      this.grantType = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> clientId = JsonNullable.undefined();

    @JsonProperty("client_id")
    public GetTokenClientCredentialsRequestBuilder clientId(String value) {
      this.clientId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> clientSecret = JsonNullable.undefined();

    @JsonProperty("client_secret")
    public GetTokenClientCredentialsRequestBuilder clientSecret(String value) {
      this.clientSecret = JsonNullable.of(value);
      return this;
    }
  }
}
