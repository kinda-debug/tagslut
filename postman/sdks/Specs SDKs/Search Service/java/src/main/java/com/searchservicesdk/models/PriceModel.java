package com.searchservicesdk.models;

import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;

@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class PriceModel {

  @NonNull
  private String code;

  @NonNull
  private String symbol;

  @NonNull
  private Double value;

  @NonNull
  private String display;
}
