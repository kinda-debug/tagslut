package com.searchservicesdk.models;

import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;
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
@NoArgsConstructor
@AllArgsConstructor
public class ValidationError {

  @NonNull
  private List<Loc> loc;

  @NonNull
  private String msg;

  @NonNull
  private String type;
}
