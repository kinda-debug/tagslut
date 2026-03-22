package com.example;

import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.exceptions.ApiError;
import com.searchservicesdk.models.HealthCheckResponse;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    try {
      HealthCheckResponse response =
        searchServiceSdk.serviceEndpoints.healthCheckSearchHealthCheckGet();

      System.out.println(response);
    } catch (ApiError e) {
      e.printStackTrace();
    }

    System.exit(0);
  }
}
