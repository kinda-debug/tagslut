package com.tagslutapisdk.http.util;

import okhttp3.MediaType;
import okhttp3.Response;

public class ContentTypes {

  private static final MediaType FALLBACK_CONTENT_TYPE = MediaType.parse("application/json");

  /**
   * Determines if the given MediaType is textual.
   * In this case, JSON is not considered textual.
   * @param contentType The MediaType to check
   * @return true if the content type is textual, false otherwise
   */
  public static boolean isTextual(MediaType contentType) {
    if (contentType == null) {
      return false;
    }

    String type = contentType.type();
    String subtype = contentType.subtype();

    if ("text".equals(type)) {
      return true;
    }

    if ("application".equals(type) && (subtype.equals("xml") || subtype.endsWith("+xml"))) {
      return true;
    }

    if ("image".equals(type) && "svg+xml".equals(subtype)) {
      return true;
    }

    if ("application".equals(type) && "javascript".equals(subtype)) {
      return true;
    }

    return false;
  }

  /**
   * Determines if the given MediaType is binary.
   * Binary types include: application/octet-stream, PDFs, images (except svg+xml), and wildcard
   *
   * @param contentType The MediaType to check
   * @return true if the content type is binary, false otherwise
   */
  public static boolean isBinary(MediaType contentType) {
    if (contentType == null) {
      return false;
    }

    String type = contentType.type();
    String subtype = contentType.subtype();

    // wildcard
    if ("*".equals(type) && "*".equals(subtype)) {
      return true;
    }

    if ("application".equals(type) && "octet-stream".equals(subtype)) {
      return true;
    }

    if ("application".equals(type) && "pdf".equals(subtype)) {
      return true;
    }

    if ("image".equals(type) && !"svg+xml".equals(subtype)) {
      return true;
    }

    return false;
  }

  public static MediaType readContentType(Response response) {
    if (response.body() != null && response.body().contentType() != null) {
      return response.body().contentType();
    }

    return FALLBACK_CONTENT_TYPE;
  }
}
