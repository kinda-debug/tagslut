package com.searchservicesdk.http.serialization;

/**
 * Enum representing OpenAPI parameter serialization styles.
 * Defines how parameters are formatted for different parts of HTTP requests.
 */
public enum SerializationStyle {
  /** Simple style - comma-separated values (default for path/header parameters) */
  SIMPLE,
  /** Label style - dot-prefixed values for path parameters (.value or .id.name) */
  LABEL,
  /** Matrix style - semicolon-prefixed key-value pairs for path parameters (;key=value) */
  MATRIX,
  /** Form style - ampersand-separated key-value pairs (default for query parameters) */
  FORM,
  /** Space-delimited style - space-separated values for query parameters */
  SPACE_DELIMITED,
  /** Pipe-delimited style - pipe-separated values for query parameters */
  PIPE_DELIMITED,
  /** Deep object style - nested objects with bracket notation (id[key]=value) */
  DEEP_OBJECT,
}
