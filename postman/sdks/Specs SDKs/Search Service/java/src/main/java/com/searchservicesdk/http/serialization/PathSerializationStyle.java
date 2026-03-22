package com.searchservicesdk.http.serialization;

/**
 * Serialization styles supported for path parameters in OpenAPI specifications.
 * Defines how values are encoded when embedded in URL paths.
 */
public enum PathSerializationStyle {
  /** Simple style - comma-separated values (default for path parameters) */
  SIMPLE(SerializationStyle.SIMPLE),
  /** Label style - dot-prefixed values (.value or .id.name) */
  LABEL(SerializationStyle.LABEL),
  /** Matrix style - semicolon-prefixed key-value pairs (;key=value) */
  MATRIX(SerializationStyle.MATRIX);

  /** The underlying serialization style */
  public final SerializationStyle style;

  PathSerializationStyle(SerializationStyle style) {
    this.style = style;
  }
}
