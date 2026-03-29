package com.example;

import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.exceptions.ApiError;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    try {
      Object response = tagslutApiSdk.auth.introspectToken();

      System.out.println(response);
    } catch (ApiError e) {
      e.printStackTrace();
    }

    System.exit(0);
  }
}
