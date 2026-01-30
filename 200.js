GET https://api.beatport.com/v4/catalog/tracks/?isrc=GBDUW0000058: {
  "Network": {
    "addresses": {
      "local": {
        "address": "192.168.18.113",
        "family": "IPv4",
        "port": 63586
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
    "host": "api.beatport.com",
    "accept": "application/json",
    "content-type": "application/json",
    "sec-fetch-site": "same-origin",
    "x-csrftoken": "7AybFF7miav2po0eOv9siF3fDM3WzMcn",
    "sec-fetch-mode": "cors",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
    "authorization": "Bearer veFg0QJZcT6juTxPoxWjUfM3kzVKwk",
    "sec-fetch-dest": "empty",
    "referer": "https://api.beatport.com/v4/docs/v4/catalog/tracks/",
    "accept-language": "en-US,en;q=0.9",
    "priority": "u=3, i",
    "accept-encoding": "gzip, deflate, br",
    "cookie": "_clsk=15pf0ul%5E1769681145556%5E3%5E0%5Eq.clarity.ms%2Fcollect; ttcsid=1769680672074::IsqOu6itsoDnJ9a2NpnB.12.1769680686308.0; ttcsid_C5TUHPGQCDCTJUG08KEG=1769680672073::sGauYRCd0T6x5kSO372D.12.1769680686308.1; ttcsid_C8G9Q1T9481MCTU3Q04G=1769680672075::fCWmUKlFjLwF36U_D97v.12.1769680686308.1; _fbp=fb.1.1769357122740.608624252200376987; _ga_GWHDKGPDMV=GS2.1.s1769680670$o15$g1$t1769680685$j46$l0$h33808432; _rdt_uuid=1769357122412.9c90a959-86f5-4cff-880b-cd95cf9370eb; QuantumMetricUserID=5f223f26cf371c7dcc8f2f0b3b21f73d; ABTasty=uid=ed9bmxpvbqkkyk4b&fst=1767911623999&pst=1769673742310&cst=1769680669251&ns=15&pvt=191&pvis=2&th=1528776.0.4.4.1.1.1769527600108.1769644474344.0.11; _evga_7282={%22uuid%22:%2247336b2d8fca6e64%22%2C%22puid%22:%226iOEhK3Sir2z3jlzi_wUSz60xPqF4mV-r6cc0d8a3Tk2awLTkNxHNT1m7LVrdVrgdUoxBoxPry0sRjvgChMp7MGv9qIp3cGWJwElkMgib0U%22%2C%22affinityId%22:%220JH%22}; _ga_R8MK3N94P6=GS2.1.s1769680670$o15$g1$t1769680682$j49$l0$h0; _sfid_9019={%22anonymousId%22:%2247336b2d8fca6e64%22%2C%22consents%22:[{%22consent%22:{%22provider%22:%22OneTrust%22%2C%22purpose%22:%22Personalization%22%2C%22status%22:%22Opt%20In%22}%2C%22lastUpdateTime%22:%222026-01-25T16:05:22.469Z%22%2C%22lastSentTime%22:%222026-01-25T16:05:22.500Z%22}]}; tms_VisitorID=2mxza0xs8x; _tt_enable_cookie=1; _ttp=01KFYAECEKBMXXD6JRHMG9PFCJ_.tt.1; OptanonConsent=isGpcEnabled=0&datestamp=Thu+Jan+29+2026+11%3A57%3A51+GMT%2B0200+(Eastern+European+Standard+Time)&version=202502.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=d3be72d3-341e-4de0-8c61-c2ebd78a0e1d&interactionCount=2&isAnonUser=1&landingPath=NotLandingPage&groups=C0004%3A1%2CC0002%3A1%2CC0003%3A1%2CC0001%3A1&intType=1&geolocation=LB%3BJL&AwaitingReconsent=false; _scid_r=m-qogR2_sIshKHEha24hqW9_ZAS5q6WEJlY-Og; _uetsid=55f77420fb0f11f0a3b08f7a8daa6d9a; _uetvid=4d2fd300fa0b11f09ad73704647520b4; _ga=GA1.1.359598546.1769357114; sessionid=qjs7mhavvk7mle6myo9z8b0uxogvgmd1; _gcl_au=1.1.1947926387.1769357122; _screload=; _clck=16jr6cn%5E2%5Eg34%5E0%5E2217; _ga_N98HW5R56D=GS2.1.s1769644656$o4$g0$t1769644656$j60$l0$h389247081; csrftoken=7AybFF7miav2po0eOv9siF3fDM3WzMcn; _ga_SKE7FF7Y22=GS2.1.s1769643991$o3$g0$t1769644478$j56$l0$h0; cf_clearance=43tjQqk66lnH6CED2Z4uQMbsOQrXG3NvtdT1IrRVfqU-1769643992-1.2.1.1-kRCKM9Ljv8kc.TuPAr7UC9mEPqVoHIA3kiu86hoLLnIB22Df.PQK5pY_1LTE4vb6U7clsny27rJhL798fCZ6lO8pPS50NUZICBLWC8TS0jc1TA0hZUMjKd0hja0hpNMuDR6MSXAiA6W9cakCU_dokjlz3pAFKHng6VelGRIISMoUNVxmeBT78TLiKLgTJjsjQIVxQcLnfbgvQUPl0hafsDHxoFuZKQSdqM3hBDte0Eo; OptanonAlertBoxClosed=2026-01-26T23:33:15.157Z; eupubconsent-v2=CQeobfAQeobfAAcABBENCPF8AP_gAAAAAChQL8QNgAhgCNAJOAg8BDoCXwE3gKbAWmAvABeYC_wGSANFAaOA6sCE4EZgI1gScAlaBPSChIKKgUXgoyCjYFHoKQApNBSgFK4KWgpfBTEFMgKaQU2BT-CoIKiQVGBUiCpYKowVUBViCrQKvQVhBWOCsoK2QVuBXECu0FeAV6gr8CwcFhQWJgsWCxsFjwWdgs-C1UFrAW7gt6C38FwQXWguwC7MF3AXdgu-C9cF7QX4AAAAAAAA.f_wAAAAAAAAA; _scid=iOqogR2_sIshKHEha24hqW9_ZAS5q6WEJlY-7A",
    "connection": "keep-alive",
    "x-postman-captr": "510822",
    "postman-token": "71f6b00b-ed77-43b6-a123-79feaa83d3b0"
  },
  "Response Headers": {
    "server": "istio-envoy",
    "date": "Thu, 29 Jan 2026 10:41:26 GMT",
    "content-type": "application/json",
    "allow": "GET, POST, HEAD, OPTIONS",
    "x-frame-options": "deny",
    "vary": "origin, Authorization",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "cross-origin-opener-policy": "unsafe-none",
    "content-encoding": "gzip",
    "x-envoy-upstream-service-time": "466",
    "x-is-canary": "false",
    "via": "1.1 google",
    "content-security-policy": "frame-ancestors 'self' btprt.dj snip.ly",
    "strict-transport-security": "max-age=31536000;includeSubDomains",
    "alt-svc": "h3=\":443\"; ma=2592000,h3-29=\":443\"; ma=2592000",
    "transfer-encoding": "chunked"
  },
  "Response Body": "{\"results\":[{\"artists\":[{\"id\":3547,\"image\":{\"id\":7297019,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\"},\"name\":\"Daft Punk\",\"slug\":\"daft-punk\",\"url\":\"https://api.beatport.com/v4/catalog/artists/3547/\"}],\"publish_status\":\"published\",\"available_worldwide\":false,\"bpm\":125,\"bsrc_remixer\":[],\"catalog_number\":\"0724384960650\",\"current_status\":{\"id\":10,\"name\":\"General Content\",\"url\":\"https://api.beatport.com/v4/auxiliary/current-status/10/\"},\"encoded_date\":\"2016-08-19T00:50:00-06:00\",\"exclusive\":false,\"free_downloads\":[],\"free_download_start_date\":null,\"free_download_end_date\":null,\"genre\":{\"id\":39,\"name\":\"Dance / Pop\",\"slug\":\"dance-pop\",\"url\":\"https://api.beatport.com/v4/catalog/genres/39/\"},\"id\":8291700,\"image\":{\"id\":14290659,\"uri\":\"https://geo-media.beatport.com/image_size/1500x250/f6951ddd-ddcb-4c79-8048-38e5f11cd3eb.png\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/f6951ddd-ddcb-4c79-8048-38e5f11cd3eb.png\"},\"is_available_for_streaming\":true,\"is_explicit\":false,\"is_ugc_remix\":false,\"is_dj_edit\":false,\"isrc\":\"GBDUW0000058\",\"key\":{\"camelot_number\":11,\"camelot_letter\":\"B\",\"chord_type\":{\"id\":2,\"name\":\"Major\",\"url\":\"https://api.beatport.com/v4/catalog/chord-types/2/\"},\"id\":23,\"is_sharp\":false,\"is_flat\":false,\"letter\":\"A\",\"name\":\"A Major\",\"url\":\"https://api.beatport.com/v4/catalog/keys/23/\"},\"label_track_identifier\":null,\"length\":\"5:01\",\"length_ms\":301373,\"mix_name\":\"Original Mix\",\"name\":\"Digital Love\",\"new_release_date\":\"2001-03-12\",\"pre_order\":false,\"pre_order_date\":\"2017-02-03\",\"price\":{\"code\":\"USD\",\"symbol\":\"$\",\"value\":1.49,\"display\":\"$1.49\"},\"publish_date\":\"2005-01-24\",\"release\":{\"id\":1835582,\"name\":\"Discovery\",\"image\":{\"id\":47530077,\"uri\":\"https://geo-media.beatport.com/image_size/1400x1400/c10fd066-6bdb-4179-b085-50ac4b5f2882.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/c10fd066-6bdb-4179-b085-50ac4b5f2882.jpg\"},\"label\":{\"id\":97547,\"name\":\"Daft Life Ltd./ADA France\",\"image\":{\"id\":5539566,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\"},\"slug\":\"daft-life-ltdada-france\"},\"slug\":\"discovery\"},\"remixers\":[],\"sale_type\":{\"id\":1,\"name\":\"purchase\",\"url\":\"https://api.beatport.com/v4/auxiliary/sale-types/1/\"},\"sample_url\":\"https://geo-samples.beatport.com/track/cd4b1b08-35c8-4e51-b2dd-c534f3eaea44.LOFI.mp3\",\"sample_start_ms\":120549,\"sample_end_ms\":240549,\"slug\":\"digital-love\",\"sub_genre\":null,\"url\":\"https://api.beatport.com/v4/catalog/tracks/8291700/\",\"is_hype\":false},{\"artists\":[{\"id\":3547,\"image\":{\"id\":7297019,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\"},\"name\":\"Daft Punk\",\"slug\":\"daft-punk\",\"url\":\"https://api.beatport.com/v4/catalog/artists/3547/\"}],\"publish_status\":\"published\",\"available_worldwide\":false,\"bpm\":125,\"bsrc_remixer\":[],\"catalog_number\":\"0094635840551\",\"current_status\":{\"id\":10,\"name\":\"General Content\",\"url\":\"https://api.beatport.com/v4/auxiliary/current-status/10/\"},\"encoded_date\":\"2014-11-05T10:58:38-07:00\",\"exclusive\":false,\"free_downloads\":[],\"free_download_start_date\":null,\"free_download_end_date\":null,\"genre\":{\"id\":39,\"name\":\"Dance / Pop\",\"slug\":\"dance-pop\",\"url\":\"https://api.beatport.com/v4/catalog/genres/39/\"},\"id\":6014317,\"image\":{\"id\":15459640,\"uri\":\"https://geo-media.beatport.com/image_size/1500x250/66e72113-d05f-4c16-a58b-67738cfb9efe.png\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/66e72113-d05f-4c16-a58b-67738cfb9efe.png\"},\"is_available_for_streaming\":true,\"is_explicit\":false,\"is_ugc_remix\":false,\"is_dj_edit\":false,\"isrc\":\"GBDUW0000058\",\"key\":{\"camelot_number\":11,\"camelot_letter\":\"B\",\"chord_type\":{\"id\":2,\"name\":\"Major\",\"url\":\"https://api.beatport.com/v4/catalog/chord-types/2/\"},\"id\":23,\"is_sharp\":false,\"is_flat\":false,\"letter\":\"A\",\"name\":\"A Major\",\"url\":\"https://api.beatport.com/v4/catalog/keys/23/\"},\"label_track_identifier\":null,\"length\":\"5:01\",\"length_ms\":301373,\"mix_name\":\"Original Mix\",\"name\":\"Digital Love\",\"new_release_date\":\"2006-04-03\",\"pre_order\":false,\"pre_order_date\":\"2017-01-29\",\"price\":{\"code\":\"USD\",\"symbol\":\"$\",\"value\":1.49,\"display\":\"$1.49\"},\"publish_date\":\"2006-04-03\",\"release\":{\"id\":1414368,\"name\":\"Musique, Vol. 1\",\"image\":{\"id\":40801117,\"uri\":\"https://geo-media.beatport.com/image_size/1400x1400/2357e8c5-fdd4-4bf1-8df4-f8160f8e4b48.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/2357e8c5-fdd4-4bf1-8df4-f8160f8e4b48.jpg\"},\"label\":{\"id\":97547,\"name\":\"Daft Life Ltd./ADA France\",\"image\":{\"id\":5539566,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\"},\"slug\":\"daft-life-ltdada-france\"},\"slug\":\"musique-vol-1\"},\"remixers\":[],\"sale_type\":{\"id\":1,\"name\":\"purchase\",\"url\":\"https://api.beatport.com/v4/auxiliary/sale-types/1/\"},\"sample_url\":\"https://geo-samples.beatport.com/track/73a1d590-f1c4-414c-8279-0af6b1ceb954.LOFI.mp3\",\"sample_start_ms\":120549,\"sample_end_ms\":210549,\"slug\":\"digital-love\",\"sub_genre\":null,\"url\":\"https://api.beatport.com/v4/catalog/tracks/6014317/\",\"is_hype\":false},{\"artists\":[{\"id\":3547,\"image\":{\"id\":7297019,\"uri\":\"https://geo-media.beatport.com/image_size/590x404/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/db2552bf-aae0-4ad4-8f44-8999db32b4b8.jpg\"},\"name\":\"Daft Punk\",\"slug\":\"daft-punk\",\"url\":\"https://api.beatport.com/v4/catalog/artists/3547/\"}],\"publish_status\":\"published\",\"available_worldwide\":false,\"bpm\":125,\"bsrc_remixer\":[],\"catalog_number\":\"0724389769951\",\"current_status\":{\"id\":10,\"name\":\"General Content\",\"url\":\"https://api.beatport.com/v4/auxiliary/current-status/10/\"},\"encoded_date\":\"2014-11-05T10:58:16-07:00\",\"exclusive\":false,\"free_downloads\":[],\"free_download_start_date\":null,\"free_download_end_date\":null,\"genre\":{\"id\":39,\"name\":\"Dance / Pop\",\"slug\":\"dance-pop\",\"url\":\"https://api.beatport.com/v4/catalog/genres/39/\"},\"id\":6014309,\"image\":{\"id\":10451083,\"uri\":\"https://geo-media.beatport.com/image_size/1500x250/d5717e4c-fa30-4881-bb17-57233c6095a6.png\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/d5717e4c-fa30-4881-bb17-57233c6095a6.png\"},\"is_available_for_streaming\":true,\"is_explicit\":false,\"is_ugc_remix\":false,\"is_dj_edit\":false,\"isrc\":\"GBDUW0000058\",\"key\":{\"camelot_number\":11,\"camelot_letter\":\"B\",\"chord_type\":{\"id\":2,\"name\":\"Major\",\"url\":\"https://api.beatport.com/v4/catalog/chord-types/2/\"},\"id\":23,\"is_sharp\":false,\"is_flat\":false,\"letter\":\"A\",\"name\":\"A Major\",\"url\":\"https://api.beatport.com/v4/catalog/keys/23/\"},\"label_track_identifier\":null,\"length\":\"5:01\",\"length_ms\":301373,\"mix_name\":\"Original Mix\",\"name\":\"Digital Love\",\"new_release_date\":\"2001-06-08\",\"pre_order\":false,\"pre_order_date\":\"2017-01-10\",\"price\":{\"code\":\"USD\",\"symbol\":\"$\",\"value\":1.49,\"display\":\"$1.49\"},\"publish_date\":\"2001-06-11\",\"release\":{\"id\":1414366,\"name\":\"Digital Love\",\"image\":{\"id\":40801233,\"uri\":\"https://geo-media.beatport.com/image_size/1400x1400/5bfbc9d0-df01-42b2-a9cd-3f62f2476047.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/5bfbc9d0-df01-42b2-a9cd-3f62f2476047.jpg\"},\"label\":{\"id\":97547,\"name\":\"Daft Life Ltd./ADA France\",\"image\":{\"id\":5539566,\"uri\":\"https://geo-media.beatport.com/image_size/500x500/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\",\"dynamic_uri\":\"https://geo-media.beatport.com/image_size/{w}x{h}/cda9862c-cf92-4d13-ac65-7e9277181f51.jpg\"},\"slug\":\"daft-life-ltdada-france\"},\"slug\":\"digital-love\"},\"remixers\":[],\"sale_type\":{\"id\":1,\"name\":\"purchase\",\"url\":\"https://api.beatport.com/v4/auxiliary/sale-types/1/\"},\"sample_url\":\"https://geo-samples.beatport.com/track/bd425bba-290c-4b1d-819f-49387f0c7714.LOFI.mp3\",\"sample_start_ms\":120549,\"sample_end_ms\":210549,\"slug\":\"digital-love\",\"sub_genre\":null,\"url\":\"https://api.beatport.com/v4/catalog/tracks/6014309/\",\"is_hype\":false}],\"next\":null,\"previous\":null,\"count\":3,\"page\":\"1/1\",\"per_page\":10}"
}
