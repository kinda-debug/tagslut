GET https://api.beatport.com/v4/catalog/tracks/?name=feeling&artist_name=Newtone: {
  "Network": {
    "addresses": {
      "local": {
        "address": "192.168.18.113",
        "family": "IPv4",
        "port": 64383
      },
      "remote": {
        "address": "34.120.11.0",
        "family": "IPv4",
        "port": 443
      }
    },
    "tls": {
      "reused": false,
      "authorized": true,
      "authorizationError": null,
      "cipher": {
        "name": "TLS_AES_128_GCM_SHA256",
        "standardName": "TLS_AES_128_GCM_SHA256",
        "version": "TLSv1/SSLv3"
      },
      "protocol": "TLSv1.3",
      "ephemeralKeyInfo": {},
      "peerCertificate": {
        "subject": {
          "country": "US",
          "stateOrProvince": "Colorado",
          "locality": "Denver",
          "organization": "Beatport, LLC",
          "organizationalUnit": null,
          "commonName": "*.beatport.com",
          "alternativeNames": "DNS:*.beatport.com, DNS:beatport.com"
        },
        "issuer": {
          "country": "US",
          "stateOrProvince": null,
          "locality": null,
          "organization": "DigiCert, Inc.",
          "organizationalUnit": null,
          "commonName": "GeoTrust G5 TLS RSA4096 SHA384 2022 CA1"
        },
        "validFrom": "Aug 26 00:00:00 2025 GMT",
        "validTo": "Sep 15 23:59:59 2026 GMT",
        "fingerprint": "9B:B3:37:38:31:45:A2:53:C4:94:97:7C:DC:9E:3E:60:88:B8:6E:03",
        "serialNumber": "0eb39867abad43d210e543199283b47e"
      }
    }
  },
  "Request Headers": {
    "content-type": "application/json",
    "accept": "application/json",
    "authorization": "Bearer veFg0QJZcT6juTxPoxWjUfM3kzVKwk",
    "referer": "https://api.beatport.com/v4/docs/v4/catalog/tracks/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
    "x-csrftoken": "7AybFF7miav2po0eOv9siF3fDM3WzMcn",
    "host": "api.beatport.com",
    "postman-token": "6ce06fc3-47eb-45be-84ec-34a1ee77da39",
    "accept-encoding": "gzip, deflate, br",
    "connection": "keep-alive"
  },
  "Response Headers": {
    "server": "istio-envoy",
    "date": "Thu, 29 Jan 2026 10:57:15 GMT",
    "content-type": "application/json",
    "allow": "GET, POST, HEAD, OPTIONS",
    "x-frame-options": "deny",
    "vary": "origin, Authorization",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "cross-origin-opener-policy": "unsafe-none",
    "content-encoding": "gzip",
    "x-envoy-upstream-service-time": "80",
    "x-is-canary": "false",
    "via": "1.1 google",
    "content-security-policy": "frame-ancestors 'self' btprt.dj snip.ly",
    "strict-transport-security": "max-age=31536000;includeSubDomains",
    "alt-svc": "h3=\":443\"; ma=2592000,h3-29=\":443\"; ma=2592000",
    "transfer-encoding": "chunked"
  },
  "Response Body": "{\"results\":[{\"artists\":[{\"id\":81853,\"image\":{\"id\":5539565,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\"},\"name\":\"Newtone\",\"slug\":\"newtone\",\"url\":\"https://api.beatport.com/v4/catalog/artists/81853/\"}],\"publish_status\":\"published\",\"available_worldwide\":false,\"bpm\":124,\"bsrc_remixer\":[],\"catalog_number\":\"BF291\",\"current_status\":{\"id\":10,\"name\":\"General Content\",\"url\":\"https://api.beatport.com/v4/auxiliary/current-status/10/\"},\"encoded_date\":\"2025-07-05T00:34:03-06:00\",\"exclusive\":false,\"free_downloads\":[],\"free_download_start_date\":null,\"free_download_end_date\":null,\"genre\":{\"id\":6,\"name\":\"Techno (Peak Time / Driving)\",\"slug\":\"techno-peak-time-driving\",\"url\":\"https://api.beatport.com/v4/catalog/genres/6/\"},\"id\":20722554,\"image\":{\"id\":43014216,\"uri\":\"https://geo-media.beatport.com/image_size/1500x250/ff39f2ad-7dd0-4995-9e19-1bd1bf1c7b68.png\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/ff39f2ad-7dd0-4995-9e19-1bd1bf1c7b68.png\"},\"is_available_for_streaming\":true,\"is_explicit\":false,\"is_ugc_remix\":false,\"is_dj_edit\":false,\"isrc\":\"NL3M12513031\",\"key\":{\"camelot_number\":12,\"camelot_letter\":\"B\",\"chord_type\":{\"id\":2,\"name\":\"Major\",\"url\":\"https://api.beatport.com/v4/catalog/chord-types/2/\"},\"id\":24,\"is_sharp\":false,\"is_flat\":false,\"letter\":\"E\",\"name\":\"E Major\",\"url\":\"https://api.beatport.com/v4/catalog/keys/24/\"},\"label_track_identifier\":\"1004985320167\",\"length\":\"7:13\",\"length_ms\":433548,\"mix_name\":\"Original Mix\",\"name\":\"Feeling\",\"new_release_date\":\"2025-08-15\",\"pre_order\":false,\"pre_order_date\":null,\"price\":{\"code\":\"USD\",\"symbol\":\"$\",\"value\":1.49,\"display\":\"$1.49\"},\"publish_date\":\"2025-08-15\",\"release\":{\"id\":5164059,\"name\":\"Feeling\",\"image\":{\"id\":43014212,\"uri\":\"https://geo-media.beatport.com/image_size/1400x1400/fb2b666f-b798-4707-acf0-2dce8107e40a.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/fb2b666f-b798-4707-acf0-2dce8107e40a.jpg\"},\"label\":{\"id\":128021,\"name\":\"Bassfeature\",\"image\":{\"id\":41700110,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/531a0428-b48d-433d-a88a-5602cfa51655.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/531a0428-b48d-433d-a88a-5602cfa51655.jpg\"},\"slug\":\"bassfeature\"},\"slug\":\"feeling\"},\"remixers\":[],\"sale_type\":{\"id\":1,\"name\":\"purchase\",\"url\":\"https://api.beatport.com/v4/auxiliary/sale-types/1/\"},\"sample_url\":\"https://geo-samples.beatport.com/track/ff39f2ad-7dd0-4995-9e19-1bd1bf1c7b68.LOFI.mp3\",\"sample_start_ms\":173419,\"sample_end_ms\":293419,\"slug\":\"feeling\",\"sub_genre\":null,\"url\":\"https://api.beatport.com/v4/catalog/tracks/20722554/\",\"is_hype\":false},{\"artists\":[{\"id\":81853,\"image\":{\"id\":5539565,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\"},\"name\":\"Newtone\",\"slug\":\"newtone\",\"url\":\"https://api.beatport.com/v4/catalog/artists/81853/\"},{\"id\":579389,\"image\":{\"id\":5539565,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/0dc61986-bccf-49d4-8fad-6b147ea8f327.jpg\"},\"name\":\"4LV\",\"slug\":\"4lv\",\"url\":\"https://api.beatport.com/v4/catalog/artists/579389/\"}],\"publish_status\":\"published\",\"available_worldwide\":true,\"bpm\":87,\"bsrc_remixer\":[],\"catalog_number\":\"CAT90141\",\"current_status\":{\"id\":10,\"name\":\"General Content\",\"url\":\"https://api.beatport.com/v4/auxiliary/current-status/10/\"},\"encoded_date\":\"2016-10-07T11:52:21-06:00\",\"exclusive\":false,\"free_downloads\":[],\"free_download_start_date\":null,\"free_download_end_date\":null,\"genre\":{\"id\":1,\"name\":\"Drum & Bass\",\"slug\":\"drum-bass\",\"url\":\"https://api.beatport.com/v4/catalog/genres/1/\"},\"id\":8476663,\"image\":{\"id\":14594556,\"uri\":\"https://geo-media.beatport.com/image_size/1500x250/0420731e-2e32-4d69-8d76-afeed9d3bd89.png\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/0420731e-2e32-4d69-8d76-afeed9d3bd89.png\"},\"is_available_for_streaming\":true,\"is_explicit\":false,\"is_ugc_remix\":false,\"is_dj_edit\":false,\"isrc\":\"QZS1Z1619388\",\"key\":{\"camelot_number\":11,\"camelot_letter\":\"A\",\"chord_type\":{\"id\":1,\"name\":\"Minor\",\"url\":\"https://api.beatport.com/v4/catalog/chord-types/1/\"},\"id\":34,\"is_sharp\":false,\"is_flat\":true,\"letter\":\"G\",\"name\":\"Gb Minor\",\"url\":\"https://api.beatport.com/v4/catalog/keys/34/\"},\"label_track_identifier\":\"524606\",\"length\":\"4:02\",\"length_ms\":242860,\"mix_name\":\"Original Mix\",\"name\":\"Feeling Good (feat. Newtone)\",\"new_release_date\":\"2016-10-11\",\"pre_order\":false,\"pre_order_date\":null,\"price\":{\"code\":\"USD\",\"symbol\":\"$\",\"value\":1.49,\"display\":\"$1.49\"},\"publish_date\":\"2016-10-11\",\"release\":{\"id\":1869010,\"name\":\"So Far\",\"image\":{\"id\":14594507,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/8cd1b3aa-c6c3-4c7a-b4b5-fb3cf1791c88.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/8cd1b3aa-c6c3-4c7a-b4b5-fb3cf1791c88.jpg\"},\"label\":{\"id\":57501,\"name\":\"Secret Family\",\"image\":{\"id\":14067208,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/710a1816-521e-4755-9981-8df7e14f168a.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/710a1816-521e-4755-9981-8df7e14f168a.jpg\"},\"slug\":\"secret-family\"},\"slug\":\"so-far\"},\"remixers\":[],\"sale_type\":{\"id\":1,\"name\":\"purchase\",\"url\":\"https://api.beatport.com/v4/auxiliary/sale-types/1/\"},\"sample_url\":\"https://geo-samples.beatport.com/track/f97ddfea-ad5b-416d-bea9-a3c6fc7df8cb.LOFI.mp3\",\"sample_start_ms\":97144,\"sample_end_ms\":217144,\"slug\":\"feeling-good-feat-newtone\",\"sub_genre\":null,\"url\":\"https://api.beatport.com/v4/catalog/tracks/8476663/\",\"is_hype\":false}],\"next\":null,\"previous\":null,\"count\":2,\"page\":\"1/1\",\"per_page\":10}"
}
