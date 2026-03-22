export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      asset_analysis: {
        Row: {
          analysis_energy_1_10: number | null
          analysis_scope: string
          analyzer: string
          analyzer_version: string
          asset_id: number
          bpm: number | null
          computed_at: string
          confidence: number | null
          id: number
          musical_key: string | null
          raw_payload_json: Json | null
        }
        Insert: {
          analysis_energy_1_10?: number | null
          analysis_scope: string
          analyzer: string
          analyzer_version: string
          asset_id: number
          bpm?: number | null
          computed_at?: string
          confidence?: number | null
          id?: number
          musical_key?: string | null
          raw_payload_json?: Json | null
        }
        Update: {
          analysis_energy_1_10?: number | null
          analysis_scope?: string
          analyzer?: string
          analyzer_version?: string
          asset_id?: number
          bpm?: number | null
          computed_at?: string
          confidence?: number | null
          id?: number
          musical_key?: string | null
          raw_payload_json?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "asset_analysis_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
        ]
      }
      asset_file: {
        Row: {
          bit_depth: number | null
          bitrate: number | null
          checksum: string | null
          chromaprint_duration_s: number | null
          chromaprint_fingerprint: string | null
          content_sha256: string | null
          download_date: string | null
          download_source: string | null
          duration_measured_ms: number | null
          duration_s: number | null
          first_seen_at: string | null
          flac_ok: boolean | null
          id: number
          integrity_checked_at: string | null
          integrity_state: string | null
          last_seen_at: string | null
          library: string | null
          mgmt_status: string | null
          mtime: number | null
          path: string
          sample_rate: number | null
          sha256_checked_at: string | null
          size_bytes: number | null
          streaminfo_checked_at: string | null
          streaminfo_md5: string | null
          zone: string | null
        }
        Insert: {
          bit_depth?: number | null
          bitrate?: number | null
          checksum?: string | null
          chromaprint_duration_s?: number | null
          chromaprint_fingerprint?: string | null
          content_sha256?: string | null
          download_date?: string | null
          download_source?: string | null
          duration_measured_ms?: number | null
          duration_s?: number | null
          first_seen_at?: string | null
          flac_ok?: boolean | null
          id?: number
          integrity_checked_at?: string | null
          integrity_state?: string | null
          last_seen_at?: string | null
          library?: string | null
          mgmt_status?: string | null
          mtime?: number | null
          path: string
          sample_rate?: number | null
          sha256_checked_at?: string | null
          size_bytes?: number | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
          zone?: string | null
        }
        Update: {
          bit_depth?: number | null
          bitrate?: number | null
          checksum?: string | null
          chromaprint_duration_s?: number | null
          chromaprint_fingerprint?: string | null
          content_sha256?: string | null
          download_date?: string | null
          download_source?: string | null
          duration_measured_ms?: number | null
          duration_s?: number | null
          first_seen_at?: string | null
          flac_ok?: boolean | null
          id?: number
          integrity_checked_at?: string | null
          integrity_state?: string | null
          last_seen_at?: string | null
          library?: string | null
          mgmt_status?: string | null
          mtime?: number | null
          path?: string
          sample_rate?: number | null
          sha256_checked_at?: string | null
          size_bytes?: number | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
          zone?: string | null
        }
        Relationships: []
      }
      asset_link: {
        Row: {
          active: boolean
          asset_id: number
          confidence: number | null
          created_at: string | null
          id: number
          identity_id: number
          link_source: string | null
          updated_at: string | null
        }
        Insert: {
          active?: boolean
          asset_id: number
          confidence?: number | null
          created_at?: string | null
          id?: number
          identity_id: number
          link_source?: string | null
          updated_at?: string | null
        }
        Update: {
          active?: boolean
          asset_id?: number
          confidence?: number | null
          created_at?: string | null
          id?: number
          identity_id?: number
          link_source?: string | null
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "asset_link_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: true
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "asset_link_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      dj_admission: {
        Row: {
          admitted_at: string | null
          created_at: string | null
          id: number
          identity_id: number | null
          mp3_asset_id: number | null
          notes: string | null
          source: string
          status: string
          updated_at: string | null
        }
        Insert: {
          admitted_at?: string | null
          created_at?: string | null
          id?: number
          identity_id?: number | null
          mp3_asset_id?: number | null
          notes?: string | null
          source?: string
          status?: string
          updated_at?: string | null
        }
        Update: {
          admitted_at?: string | null
          created_at?: string | null
          id?: number
          identity_id?: number | null
          mp3_asset_id?: number | null
          notes?: string | null
          source?: string
          status?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_admission_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_admission_mp3_asset_id_fkey"
            columns: ["mp3_asset_id"]
            isOneToOne: false
            referencedRelation: "mp3_asset"
            referencedColumns: ["id"]
          },
        ]
      }
      dj_export_state: {
        Row: {
          emitted_at: string | null
          id: number
          kind: string
          manifest_hash: string | null
          output_path: string
          scope_json: Json | null
        }
        Insert: {
          emitted_at?: string | null
          id?: number
          kind: string
          manifest_hash?: string | null
          output_path: string
          scope_json?: Json | null
        }
        Update: {
          emitted_at?: string | null
          id?: number
          kind?: string
          manifest_hash?: string | null
          output_path?: string
          scope_json?: Json | null
        }
        Relationships: []
      }
      dj_playlist: {
        Row: {
          created_at: string | null
          id: number
          lexicon_playlist_id: number | null
          name: string
          parent_id: number | null
          playlist_type: string | null
          sort_key: string | null
        }
        Insert: {
          created_at?: string | null
          id?: number
          lexicon_playlist_id?: number | null
          name: string
          parent_id?: number | null
          playlist_type?: string | null
          sort_key?: string | null
        }
        Update: {
          created_at?: string | null
          id?: number
          lexicon_playlist_id?: number | null
          name?: string
          parent_id?: number | null
          playlist_type?: string | null
          sort_key?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "dj_playlist_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "dj_playlist"
            referencedColumns: ["id"]
          },
        ]
      }
      dj_playlist_track: {
        Row: {
          dj_admission_id: number
          ordinal: number
          playlist_id: number
        }
        Insert: {
          dj_admission_id: number
          ordinal: number
          playlist_id: number
        }
        Update: {
          dj_admission_id?: number
          ordinal?: number
          playlist_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "dj_playlist_track_dj_admission_id_fkey"
            columns: ["dj_admission_id"]
            isOneToOne: false
            referencedRelation: "dj_admission"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dj_playlist_track_playlist_id_fkey"
            columns: ["playlist_id"]
            isOneToOne: false
            referencedRelation: "dj_playlist"
            referencedColumns: ["id"]
          },
        ]
      }
      dj_track_id_map: {
        Row: {
          assigned_at: string | null
          dj_admission_id: number | null
          id: number
          rekordbox_track_id: number
        }
        Insert: {
          assigned_at?: string | null
          dj_admission_id?: number | null
          id?: number
          rekordbox_track_id: number
        }
        Update: {
          assigned_at?: string | null
          dj_admission_id?: number | null
          id?: number
          rekordbox_track_id?: number
        }
        Relationships: []
      }
      dj_track_profile: {
        Row: {
          dj_tags_json: Json
          energy: number | null
          identity_id: number
          last_played_at: string | null
          notes: string | null
          rating: number | null
          set_role: string | null
          updated_at: string
        }
        Insert: {
          dj_tags_json?: Json
          energy?: number | null
          identity_id: number
          last_played_at?: string | null
          notes?: string | null
          rating?: number | null
          set_role?: string | null
          updated_at?: string
        }
        Update: {
          dj_tags_json?: Json
          energy?: number | null
          identity_id?: number
          last_played_at?: string | null
          notes?: string | null
          rating?: number | null
          set_role?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "dj_track_profile_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      file_metadata_archive: {
        Row: {
          checksum: string
          durations_json: Json
          fingerprint_json: Json | null
          first_seen_at: string
          first_seen_path: string
          identity_confidence: number
          isrc_candidates_json: Json
          quality_rank: number | null
          raw_tags_json: Json
          technical_json: Json
        }
        Insert: {
          checksum: string
          durations_json: Json
          fingerprint_json?: Json | null
          first_seen_at: string
          first_seen_path: string
          identity_confidence: number
          isrc_candidates_json: Json
          quality_rank?: number | null
          raw_tags_json: Json
          technical_json: Json
        }
        Update: {
          checksum?: string
          durations_json?: Json
          fingerprint_json?: Json | null
          first_seen_at?: string
          first_seen_path?: string
          identity_confidence?: number
          isrc_candidates_json?: Json
          quality_rank?: number | null
          raw_tags_json?: Json
          technical_json?: Json
        }
        Relationships: []
      }
      file_path_history: {
        Row: {
          checksum: string
          first_seen_at: string
          id: number
          last_seen_at: string
          path: string
        }
        Insert: {
          checksum: string
          first_seen_at: string
          id?: number
          last_seen_at: string
          path: string
        }
        Update: {
          checksum?: string
          first_seen_at?: string
          id?: number
          last_seen_at?: string
          path?: string
        }
        Relationships: []
      }
      file_quarantine: {
        Row: {
          delete_reason: string | null
          deleted_at: string | null
          id: number
          keeper_path: string | null
          original_path: string
          plan_id: string | null
          quarantine_path: string
          quarantined_at: string
          reason: string | null
          sha256: string | null
          source_zone: string | null
          tier: string | null
        }
        Insert: {
          delete_reason?: string | null
          deleted_at?: string | null
          id: number
          keeper_path?: string | null
          original_path: string
          plan_id?: string | null
          quarantine_path: string
          quarantined_at: string
          reason?: string | null
          sha256?: string | null
          source_zone?: string | null
          tier?: string | null
        }
        Update: {
          delete_reason?: string | null
          deleted_at?: string | null
          id?: number
          keeper_path?: string | null
          original_path?: string
          plan_id?: string | null
          quarantine_path?: string
          quarantined_at?: string
          reason?: string | null
          sha256?: string | null
          source_zone?: string | null
          tier?: string | null
        }
        Relationships: []
      }
      file_scan_runs: {
        Row: {
          checked_hash: boolean | null
          checked_integrity: boolean | null
          checked_metadata: boolean | null
          checked_streaminfo: boolean | null
          created_at: string | null
          error_class: string | null
          error_message: string | null
          flac_ok: boolean | null
          id: number
          integrity_checked_at: string | null
          integrity_state: string | null
          mtime: number | null
          outcome: string | null
          path: string
          session_id: number
          sha256: string | null
          sha256_checked_at: string | null
          size: number | null
          streaminfo_checked_at: string | null
          streaminfo_md5: string | null
        }
        Insert: {
          checked_hash?: boolean | null
          checked_integrity?: boolean | null
          checked_metadata?: boolean | null
          checked_streaminfo?: boolean | null
          created_at?: string | null
          error_class?: string | null
          error_message?: string | null
          flac_ok?: boolean | null
          id: number
          integrity_checked_at?: string | null
          integrity_state?: string | null
          mtime?: number | null
          outcome?: string | null
          path: string
          session_id: number
          sha256?: string | null
          sha256_checked_at?: string | null
          size?: number | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
        }
        Update: {
          checked_hash?: boolean | null
          checked_integrity?: boolean | null
          checked_metadata?: boolean | null
          checked_streaminfo?: boolean | null
          created_at?: string | null
          error_class?: string | null
          error_message?: string | null
          flac_ok?: boolean | null
          id?: number
          integrity_checked_at?: string | null
          integrity_state?: string | null
          mtime?: number | null
          outcome?: string | null
          path?: string
          session_id?: number
          sha256?: string | null
          sha256_checked_at?: string | null
          size?: number | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "file_scan_runs_session_id_fkey"
            columns: ["session_id"]
            isOneToOne: false
            referencedRelation: "scan_sessions"
            referencedColumns: ["id"]
          },
        ]
      }
      files: {
        Row: {
          acoustid: string | null
          actual_duration: number | null
          backup_path: string | null
          beatport_id: string | null
          bit_depth: number | null
          bitrate: number | null
          bpm: number | null
          canonical_acousticness: number | null
          canonical_album: string | null
          canonical_album_art_url: string | null
          canonical_artist: string | null
          canonical_bpm: number | null
          canonical_catalog_number: string | null
          canonical_danceability: number | null
          canonical_duration: number | null
          canonical_duration_source: string | null
          canonical_energy: number | null
          canonical_explicit: boolean | null
          canonical_genre: string | null
          canonical_instrumentalness: number | null
          canonical_isrc: string | null
          canonical_key: string | null
          canonical_label: string | null
          canonical_loudness: number | null
          canonical_mix_name: string | null
          canonical_release_date: string | null
          canonical_sub_genre: string | null
          canonical_title: string | null
          canonical_valence: number | null
          canonical_year: number | null
          checksum: string | null
          checksum_type: string | null
          deezer_id: string | null
          dj_flag: boolean | null
          dj_pool_path: string | null
          dj_set_role: string | null
          dj_subrole: string | null
          download_date: string | null
          download_source: string | null
          duplicate_of_checksum: string | null
          duration: number | null
          duration_check_version: string | null
          duration_delta: number | null
          duration_delta_ms: number | null
          duration_measured_at: string | null
          duration_measured_ms: number | null
          duration_ref_ms: number | null
          duration_ref_source: string | null
          duration_ref_track_id: string | null
          duration_ref_updated_at: string | null
          duration_status: string | null
          energy: number | null
          enriched_at: string | null
          enrichment_confidence: string | null
          enrichment_providers: string | null
          fingerprint: string | null
          flac_ok: boolean | null
          genre: string | null
          identity_confidence: number | null
          integrity_checked_at: string | null
          integrity_state: string | null
          is_dj_material: boolean | null
          isrc: string | null
          isrc_candidates_json: Json | null
          itunes_id: string | null
          key_camelot: string | null
          last_exported_usb: string | null
          last_scanned_at: string | null
          library: string | null
          library_track_key: string | null
          m3u_exported: string | null
          m3u_path: string | null
          metadata_health: string | null
          metadata_health_reason: string | null
          metadata_json: Json | null
          mgmt_status: string | null
          mtime: number | null
          musicbrainz_id: string | null
          new_duration: number | null
          original_path: string | null
          path: string
          pcm_md5: string | null
          qobuz_id: string | null
          quality_rank: number | null
          recovered_at: string | null
          recovery_method: string | null
          recovery_status: string | null
          rekordbox_id: number | null
          sample_rate: number | null
          scan_flags_json: Json | null
          scan_stage_reached: number | null
          scan_status: string | null
          sha256: string | null
          sha256_checked_at: string | null
          silence_events: number | null
          size: number | null
          spotify_id: string | null
          streaminfo_checked_at: string | null
          streaminfo_md5: string | null
          tidal_id: string | null
          traxsource_id: string | null
          verified_at: string | null
          zone: string | null
        }
        Insert: {
          acoustid?: string | null
          actual_duration?: number | null
          backup_path?: string | null
          beatport_id?: string | null
          bit_depth?: number | null
          bitrate?: number | null
          bpm?: number | null
          canonical_acousticness?: number | null
          canonical_album?: string | null
          canonical_album_art_url?: string | null
          canonical_artist?: string | null
          canonical_bpm?: number | null
          canonical_catalog_number?: string | null
          canonical_danceability?: number | null
          canonical_duration?: number | null
          canonical_duration_source?: string | null
          canonical_energy?: number | null
          canonical_explicit?: boolean | null
          canonical_genre?: string | null
          canonical_instrumentalness?: number | null
          canonical_isrc?: string | null
          canonical_key?: string | null
          canonical_label?: string | null
          canonical_loudness?: number | null
          canonical_mix_name?: string | null
          canonical_release_date?: string | null
          canonical_sub_genre?: string | null
          canonical_title?: string | null
          canonical_valence?: number | null
          canonical_year?: number | null
          checksum?: string | null
          checksum_type?: string | null
          deezer_id?: string | null
          dj_flag?: boolean | null
          dj_pool_path?: string | null
          dj_set_role?: string | null
          dj_subrole?: string | null
          download_date?: string | null
          download_source?: string | null
          duplicate_of_checksum?: string | null
          duration?: number | null
          duration_check_version?: string | null
          duration_delta?: number | null
          duration_delta_ms?: number | null
          duration_measured_at?: string | null
          duration_measured_ms?: number | null
          duration_ref_ms?: number | null
          duration_ref_source?: string | null
          duration_ref_track_id?: string | null
          duration_ref_updated_at?: string | null
          duration_status?: string | null
          energy?: number | null
          enriched_at?: string | null
          enrichment_confidence?: string | null
          enrichment_providers?: string | null
          fingerprint?: string | null
          flac_ok?: boolean | null
          genre?: string | null
          identity_confidence?: number | null
          integrity_checked_at?: string | null
          integrity_state?: string | null
          is_dj_material?: boolean | null
          isrc?: string | null
          isrc_candidates_json?: Json | null
          itunes_id?: string | null
          key_camelot?: string | null
          last_exported_usb?: string | null
          last_scanned_at?: string | null
          library?: string | null
          library_track_key?: string | null
          m3u_exported?: string | null
          m3u_path?: string | null
          metadata_health?: string | null
          metadata_health_reason?: string | null
          metadata_json?: Json | null
          mgmt_status?: string | null
          mtime?: number | null
          musicbrainz_id?: string | null
          new_duration?: number | null
          original_path?: string | null
          path: string
          pcm_md5?: string | null
          qobuz_id?: string | null
          quality_rank?: number | null
          recovered_at?: string | null
          recovery_method?: string | null
          recovery_status?: string | null
          rekordbox_id?: number | null
          sample_rate?: number | null
          scan_flags_json?: Json | null
          scan_stage_reached?: number | null
          scan_status?: string | null
          sha256?: string | null
          sha256_checked_at?: string | null
          silence_events?: number | null
          size?: number | null
          spotify_id?: string | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
          tidal_id?: string | null
          traxsource_id?: string | null
          verified_at?: string | null
          zone?: string | null
        }
        Update: {
          acoustid?: string | null
          actual_duration?: number | null
          backup_path?: string | null
          beatport_id?: string | null
          bit_depth?: number | null
          bitrate?: number | null
          bpm?: number | null
          canonical_acousticness?: number | null
          canonical_album?: string | null
          canonical_album_art_url?: string | null
          canonical_artist?: string | null
          canonical_bpm?: number | null
          canonical_catalog_number?: string | null
          canonical_danceability?: number | null
          canonical_duration?: number | null
          canonical_duration_source?: string | null
          canonical_energy?: number | null
          canonical_explicit?: boolean | null
          canonical_genre?: string | null
          canonical_instrumentalness?: number | null
          canonical_isrc?: string | null
          canonical_key?: string | null
          canonical_label?: string | null
          canonical_loudness?: number | null
          canonical_mix_name?: string | null
          canonical_release_date?: string | null
          canonical_sub_genre?: string | null
          canonical_title?: string | null
          canonical_valence?: number | null
          canonical_year?: number | null
          checksum?: string | null
          checksum_type?: string | null
          deezer_id?: string | null
          dj_flag?: boolean | null
          dj_pool_path?: string | null
          dj_set_role?: string | null
          dj_subrole?: string | null
          download_date?: string | null
          download_source?: string | null
          duplicate_of_checksum?: string | null
          duration?: number | null
          duration_check_version?: string | null
          duration_delta?: number | null
          duration_delta_ms?: number | null
          duration_measured_at?: string | null
          duration_measured_ms?: number | null
          duration_ref_ms?: number | null
          duration_ref_source?: string | null
          duration_ref_track_id?: string | null
          duration_ref_updated_at?: string | null
          duration_status?: string | null
          energy?: number | null
          enriched_at?: string | null
          enrichment_confidence?: string | null
          enrichment_providers?: string | null
          fingerprint?: string | null
          flac_ok?: boolean | null
          genre?: string | null
          identity_confidence?: number | null
          integrity_checked_at?: string | null
          integrity_state?: string | null
          is_dj_material?: boolean | null
          isrc?: string | null
          isrc_candidates_json?: Json | null
          itunes_id?: string | null
          key_camelot?: string | null
          last_exported_usb?: string | null
          last_scanned_at?: string | null
          library?: string | null
          library_track_key?: string | null
          m3u_exported?: string | null
          m3u_path?: string | null
          metadata_health?: string | null
          metadata_health_reason?: string | null
          metadata_json?: Json | null
          mgmt_status?: string | null
          mtime?: number | null
          musicbrainz_id?: string | null
          new_duration?: number | null
          original_path?: string | null
          path?: string
          pcm_md5?: string | null
          qobuz_id?: string | null
          quality_rank?: number | null
          recovered_at?: string | null
          recovery_method?: string | null
          recovery_status?: string | null
          rekordbox_id?: number | null
          sample_rate?: number | null
          scan_flags_json?: Json | null
          scan_stage_reached?: number | null
          scan_status?: string | null
          sha256?: string | null
          sha256_checked_at?: string | null
          silence_events?: number | null
          size?: number | null
          spotify_id?: string | null
          streaminfo_checked_at?: string | null
          streaminfo_md5?: string | null
          tidal_id?: string | null
          traxsource_id?: string | null
          verified_at?: string | null
          zone?: string | null
        }
        Relationships: []
      }
      gig_set_tracks: {
        Row: {
          exported_at: string | null
          file_path: string
          gig_set_id: number
          id: number
          mp3_path: string | null
          rekordbox_id: number | null
          transcoded_at: string | null
          usb_dest_path: string | null
        }
        Insert: {
          exported_at?: string | null
          file_path: string
          gig_set_id: number
          id?: number
          mp3_path?: string | null
          rekordbox_id?: number | null
          transcoded_at?: string | null
          usb_dest_path?: string | null
        }
        Update: {
          exported_at?: string | null
          file_path?: string
          gig_set_id?: number
          id?: number
          mp3_path?: string | null
          rekordbox_id?: number | null
          transcoded_at?: string | null
          usb_dest_path?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "gig_set_tracks_gig_set_id_fkey"
            columns: ["gig_set_id"]
            isOneToOne: false
            referencedRelation: "gig_sets"
            referencedColumns: ["id"]
          },
        ]
      }
      gig_sets: {
        Row: {
          created_at: string | null
          exported_at: string | null
          filter_expr: string | null
          id: number
          manifest_path: string | null
          name: string
          track_count: number | null
          usb_path: string | null
        }
        Insert: {
          created_at?: string | null
          exported_at?: string | null
          filter_expr?: string | null
          id?: number
          manifest_path?: string | null
          name: string
          track_count?: number | null
          usb_path?: string | null
        }
        Update: {
          created_at?: string | null
          exported_at?: string | null
          filter_expr?: string | null
          id?: number
          manifest_path?: string | null
          name?: string
          track_count?: number | null
          usb_path?: string | null
        }
        Relationships: []
      }
      gigs: {
        Row: {
          bpm_max: number | null
          bpm_min: number | null
          created_at: string | null
          date: string
          id: number
          output_path: string | null
          roles_filter: string | null
          track_count: number | null
          venue: string | null
        }
        Insert: {
          bpm_max?: number | null
          bpm_min?: number | null
          created_at?: string | null
          date: string
          id?: number
          output_path?: string | null
          roles_filter?: string | null
          track_count?: number | null
          venue?: string | null
        }
        Update: {
          bpm_max?: number | null
          bpm_min?: number | null
          created_at?: string | null
          date?: string
          id?: number
          output_path?: string | null
          roles_filter?: string | null
          track_count?: number | null
          venue?: string | null
        }
        Relationships: []
      }
      identity_merge_log: {
        Row: {
          assets_moved: number
          dry_run: boolean
          fields_copied_json: Json | null
          id: number
          key_value: string
          loser_identity_ids: string
          merge_type: string
          merged_at: string | null
          rationale_json: Json | null
          winner_identity_id: number
        }
        Insert: {
          assets_moved: number
          dry_run?: boolean
          fields_copied_json?: Json | null
          id?: number
          key_value: string
          loser_identity_ids: string
          merge_type: string
          merged_at?: string | null
          rationale_json?: Json | null
          winner_identity_id: number
        }
        Update: {
          assets_moved?: number
          dry_run?: boolean
          fields_copied_json?: Json | null
          id?: number
          key_value?: string
          loser_identity_ids?: string
          merge_type?: string
          merged_at?: string | null
          rationale_json?: Json | null
          winner_identity_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_merge_log_winner_identity_id_fkey"
            columns: ["winner_identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      identity_status: {
        Row: {
          computed_at: string
          identity_id: number
          reason_json: Json
          status: string
          version: number
        }
        Insert: {
          computed_at?: string
          identity_id: number
          reason_json?: Json
          status: string
          version: number
        }
        Update: {
          computed_at?: string
          identity_id?: number
          reason_json?: Json
          status?: string
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "identity_status_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      library_track_sources: {
        Row: {
          fetched_at: string | null
          id: number
          identity_key: string
          match_confidence: string | null
          metadata_json: Json | null
          provider: string
          provider_track_id: string
          raw_payload_json: Json | null
          source_url: string | null
        }
        Insert: {
          fetched_at?: string | null
          id?: number
          identity_key: string
          match_confidence?: string | null
          metadata_json?: Json | null
          provider: string
          provider_track_id: string
          raw_payload_json?: Json | null
          source_url?: string | null
        }
        Update: {
          fetched_at?: string | null
          id?: number
          identity_key?: string
          match_confidence?: string | null
          metadata_json?: Json | null
          provider?: string
          provider_track_id?: string
          raw_payload_json?: Json | null
          source_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_key"]
          },
          {
            foreignKeyName: "library_track_sources_identity_key_fkey"
            columns: ["identity_key"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_key"]
          },
        ]
      }
      library_tracks: {
        Row: {
          album: string | null
          artist: string | null
          best_cover_url: string | null
          bpm: number | null
          created_at: string | null
          duration_ms: number | null
          explicit: boolean | null
          genre: string | null
          id: number
          isrc: string | null
          label: string | null
          library_track_key: string | null
          lyrics_excerpt: string | null
          musical_key: string | null
          release_date: string | null
          title: string | null
          updated_at: string | null
        }
        Insert: {
          album?: string | null
          artist?: string | null
          best_cover_url?: string | null
          bpm?: number | null
          created_at?: string | null
          duration_ms?: number | null
          explicit?: boolean | null
          genre?: string | null
          id?: number
          isrc?: string | null
          label?: string | null
          library_track_key?: string | null
          lyrics_excerpt?: string | null
          musical_key?: string | null
          release_date?: string | null
          title?: string | null
          updated_at?: string | null
        }
        Update: {
          album?: string | null
          artist?: string | null
          best_cover_url?: string | null
          bpm?: number | null
          created_at?: string | null
          duration_ms?: number | null
          explicit?: boolean | null
          genre?: string | null
          id?: number
          isrc?: string | null
          label?: string | null
          library_track_key?: string | null
          lyrics_excerpt?: string | null
          musical_key?: string | null
          release_date?: string | null
          title?: string | null
          updated_at?: string | null
        }
        Relationships: []
      }
      migration_progress: {
        Row: {
          assets_migrated: number
          batch_size: number
          completed_at: string | null
          enrichment_preserved_count: number
          id: number
          identities_created: number
          integrity_preserved_count: number
          is_complete: boolean
          last_v2_path: string | null
          last_v2_rowid: number
          library_sources_done: number
          move_tables_done: number
          started_at: string | null
          unidentified_count: number
          updated_at: string | null
          v2_path: string
          v3_path: string
        }
        Insert: {
          assets_migrated?: number
          batch_size: number
          completed_at?: string | null
          enrichment_preserved_count?: number
          id: number
          identities_created?: number
          integrity_preserved_count?: number
          is_complete?: boolean
          last_v2_path?: string | null
          last_v2_rowid?: number
          library_sources_done?: number
          move_tables_done?: number
          started_at?: string | null
          unidentified_count?: number
          updated_at?: string | null
          v2_path: string
          v3_path: string
        }
        Update: {
          assets_migrated?: number
          batch_size?: number
          completed_at?: string | null
          enrichment_preserved_count?: number
          id?: number
          identities_created?: number
          integrity_preserved_count?: number
          is_complete?: boolean
          last_v2_path?: string | null
          last_v2_rowid?: number
          library_sources_done?: number
          move_tables_done?: number
          started_at?: string | null
          unidentified_count?: number
          updated_at?: string | null
          v2_path?: string
          v3_path?: string
        }
        Relationships: []
      }
      migrations_applied: {
        Row: {
          applied_at: string | null
          id: number
          name: string | null
        }
        Insert: {
          applied_at?: string | null
          id: number
          name?: string | null
        }
        Update: {
          applied_at?: string | null
          id?: number
          name?: string | null
        }
        Relationships: []
      }
      move_execution: {
        Row: {
          action: string | null
          asset_id: number | null
          dest_path: string | null
          details_json: Json | null
          error: string | null
          executed_at: string | null
          id: number
          plan_id: number | null
          source_path: string | null
          status: string
          verification: string | null
        }
        Insert: {
          action?: string | null
          asset_id?: number | null
          dest_path?: string | null
          details_json?: Json | null
          error?: string | null
          executed_at?: string | null
          id?: number
          plan_id?: number | null
          source_path?: string | null
          status: string
          verification?: string | null
        }
        Update: {
          action?: string | null
          asset_id?: number | null
          dest_path?: string | null
          details_json?: Json | null
          error?: string | null
          executed_at?: string | null
          id?: number
          plan_id?: number | null
          source_path?: string | null
          status?: string
          verification?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "move_execution_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "move_execution_plan_id_fkey"
            columns: ["plan_id"]
            isOneToOne: false
            referencedRelation: "move_plan"
            referencedColumns: ["id"]
          },
        ]
      }
      move_plan: {
        Row: {
          context_json: Json | null
          created_at: string | null
          id: number
          plan_key: string
          plan_path: string | null
          plan_type: string | null
          policy_version: string | null
        }
        Insert: {
          context_json?: Json | null
          created_at?: string | null
          id?: number
          plan_key: string
          plan_path?: string | null
          plan_type?: string | null
          policy_version?: string | null
        }
        Update: {
          context_json?: Json | null
          created_at?: string | null
          id?: number
          plan_key?: string
          plan_path?: string | null
          plan_type?: string | null
          policy_version?: string | null
        }
        Relationships: []
      }
      mp3_asset: {
        Row: {
          asset_id: number | null
          bitrate: number | null
          content_sha256: string | null
          created_at: string | null
          duration_s: number | null
          id: number
          identity_id: number | null
          lexicon_track_id: number | null
          path: string
          profile: string
          reconciled_at: string | null
          sample_rate: number | null
          size_bytes: number | null
          source: string
          status: string
          transcoded_at: string | null
          updated_at: string | null
          zone: string | null
        }
        Insert: {
          asset_id?: number | null
          bitrate?: number | null
          content_sha256?: string | null
          created_at?: string | null
          duration_s?: number | null
          id?: number
          identity_id?: number | null
          lexicon_track_id?: number | null
          path: string
          profile?: string
          reconciled_at?: string | null
          sample_rate?: number | null
          size_bytes?: number | null
          source?: string
          status?: string
          transcoded_at?: string | null
          updated_at?: string | null
          zone?: string | null
        }
        Update: {
          asset_id?: number | null
          bitrate?: number | null
          content_sha256?: string | null
          created_at?: string | null
          duration_s?: number | null
          id?: number
          identity_id?: number | null
          lexicon_track_id?: number | null
          path?: string
          profile?: string
          reconciled_at?: string | null
          sample_rate?: number | null
          size_bytes?: number | null
          source?: string
          status?: string
          transcoded_at?: string | null
          updated_at?: string | null
          zone?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "mp3_asset_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "mp3_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      preferred_asset: {
        Row: {
          asset_id: number
          computed_at: string | null
          identity_id: number
          reason_json: Json
          score: number
          version: number
        }
        Insert: {
          asset_id: number
          computed_at?: string | null
          identity_id: number
          reason_json: Json
          score: number
          version: number
        }
        Update: {
          asset_id?: number
          computed_at?: string | null
          identity_id?: number
          reason_json?: Json
          score?: number
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "preferred_asset_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: true
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      promotions: {
        Row: {
          dest_path: string
          id: number
          mode: string
          source_path: string
          timestamp: string
        }
        Insert: {
          dest_path: string
          id?: number
          mode: string
          source_path: string
          timestamp: string
        }
        Update: {
          dest_path?: string
          id?: number
          mode?: string
          source_path?: string
          timestamp?: string
        }
        Relationships: []
      }
      provenance_event: {
        Row: {
          asset_id: number | null
          dest_path: string | null
          details_json: Json | null
          event_time: string | null
          event_type: string
          id: number
          identity_id: number | null
          move_execution_id: number | null
          move_plan_id: number | null
          source_path: string | null
          status: string | null
        }
        Insert: {
          asset_id?: number | null
          dest_path?: string | null
          details_json?: Json | null
          event_time?: string | null
          event_type: string
          id?: number
          identity_id?: number | null
          move_execution_id?: number | null
          move_plan_id?: number | null
          source_path?: string | null
          status?: string | null
        }
        Update: {
          asset_id?: number | null
          dest_path?: string | null
          details_json?: Json | null
          event_time?: string | null
          event_type?: string
          id?: number
          identity_id?: number | null
          move_execution_id?: number | null
          move_plan_id?: number | null
          source_path?: string | null
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "provenance_event_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "provenance_event_identity_id_fkey"
            columns: ["identity_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "provenance_event_move_execution_id_fkey"
            columns: ["move_execution_id"]
            isOneToOne: false
            referencedRelation: "move_execution"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "provenance_event_move_plan_id_fkey"
            columns: ["move_plan_id"]
            isOneToOne: false
            referencedRelation: "move_plan"
            referencedColumns: ["id"]
          },
        ]
      }
      reconcile_log: {
        Row: {
          action: string
          confidence: string | null
          details_json: Json | null
          event_time: string | null
          id: number
          identity_id: number | null
          lexicon_track_id: number | null
          mp3_path: string | null
          run_id: string
          source: string
        }
        Insert: {
          action: string
          confidence?: string | null
          details_json?: Json | null
          event_time?: string | null
          id?: number
          identity_id?: number | null
          lexicon_track_id?: number | null
          mp3_path?: string | null
          run_id: string
          source: string
        }
        Update: {
          action?: string
          confidence?: string | null
          details_json?: Json | null
          event_time?: string | null
          id?: number
          identity_id?: number | null
          lexicon_track_id?: number | null
          mp3_path?: string | null
          run_id?: string
          source?: string
        }
        Relationships: []
      }
      scan_issues: {
        Row: {
          created_at: string | null
          evidence_json: Json | null
          id: number
          issue_code: string
          path: string | null
          queue_id: number | null
          run_id: number
          severity: string
        }
        Insert: {
          created_at?: string | null
          evidence_json?: Json | null
          id?: number
          issue_code: string
          path?: string | null
          queue_id?: number | null
          run_id: number
          severity?: string
        }
        Update: {
          created_at?: string | null
          evidence_json?: Json | null
          id?: number
          issue_code?: string
          path?: string | null
          queue_id?: number | null
          run_id?: number
          severity?: string
        }
        Relationships: [
          {
            foreignKeyName: "scan_issues_queue_id_fkey"
            columns: ["queue_id"]
            isOneToOne: false
            referencedRelation: "scan_queue"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "scan_issues_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "scan_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      scan_queue: {
        Row: {
          created_at: string | null
          id: number
          last_error: string | null
          mtime_ns: number | null
          path: string
          run_id: number
          size_bytes: number | null
          stage: string
          state: string
          updated_at: string | null
        }
        Insert: {
          created_at?: string | null
          id?: number
          last_error?: string | null
          mtime_ns?: number | null
          path: string
          run_id: number
          size_bytes?: number | null
          stage?: string
          state?: string
          updated_at?: string | null
        }
        Update: {
          created_at?: string | null
          id?: number
          last_error?: string | null
          mtime_ns?: number | null
          path?: string
          run_id?: number
          size_bytes?: number | null
          stage?: string
          state?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "scan_queue_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "scan_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      scan_runs: {
        Row: {
          completed_at: string | null
          created_at: string | null
          id: number
          library_root: string | null
          metadata_json: Json | null
          mode: string
          started_at: string | null
          status: string
          tool_versions_json: Json | null
        }
        Insert: {
          completed_at?: string | null
          created_at?: string | null
          id?: number
          library_root?: string | null
          metadata_json?: Json | null
          mode?: string
          started_at?: string | null
          status?: string
          tool_versions_json?: Json | null
        }
        Update: {
          completed_at?: string | null
          created_at?: string | null
          id?: number
          library_root?: string | null
          metadata_json?: Json | null
          mode?: string
          started_at?: string | null
          status?: string
          tool_versions_json?: Json | null
        }
        Relationships: []
      }
      scan_sessions: {
        Row: {
          considered: number | null
          db_path: string | null
          discovered: number | null
          ended_at: string | null
          failed: number | null
          finished_at: string | null
          force_all: boolean | null
          host: string | null
          id: number
          incremental: boolean | null
          library: string | null
          paths_from_file: string | null
          paths_source: string | null
          recheck: boolean | null
          root_path: string | null
          scan_hash: boolean | null
          scan_integrity: boolean | null
          scan_limit: number | null
          skipped: number | null
          started_at: string | null
          status: string | null
          succeeded: number | null
          updated: number | null
          zone: string | null
        }
        Insert: {
          considered?: number | null
          db_path?: string | null
          discovered?: number | null
          ended_at?: string | null
          failed?: number | null
          finished_at?: string | null
          force_all?: boolean | null
          host?: string | null
          id: number
          incremental?: boolean | null
          library?: string | null
          paths_from_file?: string | null
          paths_source?: string | null
          recheck?: boolean | null
          root_path?: string | null
          scan_hash?: boolean | null
          scan_integrity?: boolean | null
          scan_limit?: number | null
          skipped?: number | null
          started_at?: string | null
          status?: string | null
          succeeded?: number | null
          updated?: number | null
          zone?: string | null
        }
        Update: {
          considered?: number | null
          db_path?: string | null
          discovered?: number | null
          ended_at?: string | null
          failed?: number | null
          finished_at?: string | null
          force_all?: boolean | null
          host?: string | null
          id?: number
          incremental?: boolean | null
          library?: string | null
          paths_from_file?: string | null
          paths_source?: string | null
          recheck?: boolean | null
          root_path?: string | null
          scan_hash?: boolean | null
          scan_integrity?: boolean | null
          scan_limit?: number | null
          skipped?: number | null
          started_at?: string | null
          status?: string | null
          succeeded?: number | null
          updated?: number | null
          zone?: string | null
        }
        Relationships: []
      }
      scan_trust_batches: {
        Row: {
          allow_accepted: boolean | null
          created_at: string | null
          db_path: string | null
          id: number
          root_path: string | null
          trust_post: number | null
          trust_pre: number | null
        }
        Insert: {
          allow_accepted?: boolean | null
          created_at?: string | null
          db_path?: string | null
          id?: number
          root_path?: string | null
          trust_post?: number | null
          trust_pre?: number | null
        }
        Update: {
          allow_accepted?: boolean | null
          created_at?: string | null
          db_path?: string | null
          id?: number
          root_path?: string | null
          trust_post?: number | null
          trust_pre?: number | null
        }
        Relationships: []
      }
      schema_migrations: {
        Row: {
          applied_at: string | null
          id: number
          note: string | null
          schema_name: string
          version: number
        }
        Insert: {
          applied_at?: string | null
          id: number
          note?: string | null
          schema_name: string
          version: number
        }
        Update: {
          applied_at?: string | null
          id?: number
          note?: string | null
          schema_name?: string
          version?: number
        }
        Relationships: []
      }
      tag_hoard_files: {
        Row: {
          path: string | null
          run_id: number | null
          tags_json: Json | null
        }
        Insert: {
          path?: string | null
          run_id?: number | null
          tags_json?: Json | null
        }
        Update: {
          path?: string | null
          run_id?: number | null
          tags_json?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "tag_hoard_files_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "tag_hoard_runs"
            referencedColumns: ["run_id"]
          },
        ]
      }
      tag_hoard_keys: {
        Row: {
          files_with_tag: number | null
          run_id: number
          tag: string
          unique_values: number | null
        }
        Insert: {
          files_with_tag?: number | null
          run_id: number
          tag: string
          unique_values?: number | null
        }
        Update: {
          files_with_tag?: number | null
          run_id?: number
          tag?: string
          unique_values?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "tag_hoard_keys_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "tag_hoard_runs"
            referencedColumns: ["run_id"]
          },
        ]
      }
      tag_hoard_runs: {
        Row: {
          created_at: string | null
          extensions_json: Json | null
          max_files: number | null
          max_value_len: number | null
          roots_json: Json | null
          run_id: number
          scanned_files: number | null
          workers: number | null
        }
        Insert: {
          created_at?: string | null
          extensions_json?: Json | null
          max_files?: number | null
          max_value_len?: number | null
          roots_json?: Json | null
          run_id?: number
          scanned_files?: number | null
          workers?: number | null
        }
        Update: {
          created_at?: string | null
          extensions_json?: Json | null
          max_files?: number | null
          max_value_len?: number | null
          roots_json?: Json | null
          run_id?: number
          scanned_files?: number | null
          workers?: number | null
        }
        Relationships: []
      }
      tag_hoard_values: {
        Row: {
          count: number | null
          run_id: number
          tag: string
          value: string
        }
        Insert: {
          count?: number | null
          run_id: number
          tag: string
          value: string
        }
        Update: {
          count?: number | null
          run_id?: number
          tag?: string
          value?: string
        }
        Relationships: [
          {
            foreignKeyName: "tag_hoard_values_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "tag_hoard_runs"
            referencedColumns: ["run_id"]
          },
        ]
      }
      track_duration_refs: {
        Row: {
          duration_ref_ms: number
          ref_id: string
          ref_source: string
          ref_type: string
          ref_updated_at: string | null
        }
        Insert: {
          duration_ref_ms: number
          ref_id: string
          ref_source: string
          ref_type: string
          ref_updated_at?: string | null
        }
        Update: {
          duration_ref_ms?: number
          ref_id?: string
          ref_source?: string
          ref_type?: string
          ref_updated_at?: string | null
        }
        Relationships: []
      }
      track_identity: {
        Row: {
          album_norm: string | null
          apple_music_id: string | null
          artist_norm: string | null
          beatport_id: string | null
          canonical_album: string | null
          canonical_artist: string | null
          canonical_bpm: number | null
          canonical_catalog_number: string | null
          canonical_duration: number | null
          canonical_genre: string | null
          canonical_key: string | null
          canonical_label: string | null
          canonical_mix_name: string | null
          canonical_payload_json: Json | null
          canonical_release_date: string | null
          canonical_sub_genre: string | null
          canonical_title: string | null
          canonical_year: number | null
          created_at: string | null
          deezer_id: string | null
          duration_ref_ms: number | null
          enriched_at: string | null
          id: number
          identity_key: string
          isrc: string | null
          itunes_id: string | null
          merged_into_id: number | null
          musicbrainz_id: string | null
          qobuz_id: string | null
          ref_source: string | null
          spotify_id: string | null
          tidal_id: string | null
          title_norm: string | null
          traxsource_id: string | null
          updated_at: string | null
        }
        Insert: {
          album_norm?: string | null
          apple_music_id?: string | null
          artist_norm?: string | null
          beatport_id?: string | null
          canonical_album?: string | null
          canonical_artist?: string | null
          canonical_bpm?: number | null
          canonical_catalog_number?: string | null
          canonical_duration?: number | null
          canonical_genre?: string | null
          canonical_key?: string | null
          canonical_label?: string | null
          canonical_mix_name?: string | null
          canonical_payload_json?: Json | null
          canonical_release_date?: string | null
          canonical_sub_genre?: string | null
          canonical_title?: string | null
          canonical_year?: number | null
          created_at?: string | null
          deezer_id?: string | null
          duration_ref_ms?: number | null
          enriched_at?: string | null
          id?: number
          identity_key: string
          isrc?: string | null
          itunes_id?: string | null
          merged_into_id?: number | null
          musicbrainz_id?: string | null
          qobuz_id?: string | null
          ref_source?: string | null
          spotify_id?: string | null
          tidal_id?: string | null
          title_norm?: string | null
          traxsource_id?: string | null
          updated_at?: string | null
        }
        Update: {
          album_norm?: string | null
          apple_music_id?: string | null
          artist_norm?: string | null
          beatport_id?: string | null
          canonical_album?: string | null
          canonical_artist?: string | null
          canonical_bpm?: number | null
          canonical_catalog_number?: string | null
          canonical_duration?: number | null
          canonical_genre?: string | null
          canonical_key?: string | null
          canonical_label?: string | null
          canonical_mix_name?: string | null
          canonical_payload_json?: Json | null
          canonical_release_date?: string | null
          canonical_sub_genre?: string | null
          canonical_title?: string | null
          canonical_year?: number | null
          created_at?: string | null
          deezer_id?: string | null
          duration_ref_ms?: number | null
          enriched_at?: string | null
          id?: number
          identity_key?: string
          isrc?: string | null
          itunes_id?: string | null
          merged_into_id?: number | null
          musicbrainz_id?: string | null
          qobuz_id?: string | null
          ref_source?: string | null
          spotify_id?: string | null
          tidal_id?: string | null
          title_norm?: string | null
          traxsource_id?: string | null
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
    }
    Views: {
      v_active_identity: {
        Row: {
          album_norm: string | null
          apple_music_id: string | null
          artist_norm: string | null
          beatport_id: string | null
          canonical_album: string | null
          canonical_artist: string | null
          canonical_bpm: number | null
          canonical_catalog_number: string | null
          canonical_duration: number | null
          canonical_genre: string | null
          canonical_key: string | null
          canonical_label: string | null
          canonical_mix_name: string | null
          canonical_payload_json: Json | null
          canonical_release_date: string | null
          canonical_sub_genre: string | null
          canonical_title: string | null
          canonical_year: number | null
          created_at: string | null
          deezer_id: string | null
          duration_ref_ms: number | null
          enriched_at: string | null
          id: number | null
          identity_key: string | null
          isrc: string | null
          itunes_id: string | null
          merged_into_id: number | null
          musicbrainz_id: string | null
          qobuz_id: string | null
          ref_source: string | null
          spotify_id: string | null
          tidal_id: string | null
          title_norm: string | null
          traxsource_id: string | null
          updated_at: string | null
        }
        Relationships: [
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      v_asset_analysis_latest_dj: {
        Row: {
          analysis_energy_1_10: number | null
          analysis_scope: string | null
          analyzer: string | null
          analyzer_version: string | null
          asset_id: number | null
          bpm: number | null
          computed_at: string | null
          confidence: number | null
          id: number | null
          musical_key: string | null
          raw_payload_json: Json | null
        }
        Insert: {
          analysis_energy_1_10?: number | null
          analysis_scope?: string | null
          analyzer?: string | null
          analyzer_version?: string | null
          asset_id?: number | null
          bpm?: number | null
          computed_at?: string | null
          confidence?: number | null
          id?: number | null
          musical_key?: string | null
          raw_payload_json?: Json | null
        }
        Update: {
          analysis_energy_1_10?: number | null
          analysis_scope?: string | null
          analyzer?: string | null
          analyzer_version?: string | null
          asset_id?: number | null
          bpm?: number | null
          computed_at?: string | null
          confidence?: number | null
          id?: number | null
          musical_key?: string | null
          raw_payload_json?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "asset_analysis_asset_id_fkey"
            columns: ["asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
        ]
      }
      v_dj_export_metadata_v1: {
        Row: {
          album: string | null
          analysis_analyzer: string | null
          analysis_computed_at: string | null
          artist: string | null
          bpm_source: string | null
          energy_source: string | null
          export_bpm: number | null
          export_energy: number | null
          export_key: string | null
          genre: string | null
          identity_id: number | null
          identity_key: string | null
          isrc: string | null
          key_source: string | null
          label: string | null
          preferred_asset_id: number | null
          preferred_path: string | null
          title: string | null
          year: number | null
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["preferred_asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
        ]
      }
      v_dj_pool_candidates_active_orphan_v3: {
        Row: {
          album: string | null
          artist: string | null
          asset_mtime: number | null
          asset_path: string | null
          beatport_id: string | null
          bit_depth: number | null
          bitrate: number | null
          bpm: number | null
          dj_energy: number | null
          dj_last_played_at: string | null
          dj_notes: string | null
          dj_rating: number | null
          dj_set_role: string | null
          dj_tags_json: Json | null
          dj_updated_at: string | null
          duration_s: number | null
          first_seen_at: string | null
          genre: string | null
          identity_created_at: string | null
          identity_enriched_at: string | null
          identity_id: number | null
          identity_key: string | null
          identity_status: string | null
          identity_updated_at: string | null
          integrity_checked_at: string | null
          integrity_state: string | null
          isrc: string | null
          last_seen_at: string | null
          merged_into_id: number | null
          mix_name: string | null
          musical_key: string | null
          preferred_asset_id: number | null
          sample_rate: number | null
          sha256: string | null
          sub_genre: string | null
          title: string | null
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["preferred_asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      v_dj_pool_candidates_active_v3: {
        Row: {
          album: string | null
          artist: string | null
          asset_mtime: number | null
          asset_path: string | null
          beatport_id: string | null
          bit_depth: number | null
          bitrate: number | null
          bpm: number | null
          dj_energy: number | null
          dj_last_played_at: string | null
          dj_notes: string | null
          dj_rating: number | null
          dj_set_role: string | null
          dj_tags_json: Json | null
          dj_updated_at: string | null
          duration_s: number | null
          first_seen_at: string | null
          genre: string | null
          identity_created_at: string | null
          identity_enriched_at: string | null
          identity_id: number | null
          identity_key: string | null
          identity_status: string | null
          identity_updated_at: string | null
          integrity_checked_at: string | null
          integrity_state: string | null
          isrc: string | null
          last_seen_at: string | null
          merged_into_id: number | null
          mix_name: string | null
          musical_key: string | null
          preferred_asset_id: number | null
          sample_rate: number | null
          sha256: string | null
          sub_genre: string | null
          title: string | null
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["preferred_asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      v_dj_pool_candidates_v3: {
        Row: {
          album: string | null
          artist: string | null
          asset_mtime: number | null
          asset_path: string | null
          beatport_id: string | null
          bit_depth: number | null
          bitrate: number | null
          bpm: number | null
          dj_energy: number | null
          dj_last_played_at: string | null
          dj_notes: string | null
          dj_rating: number | null
          dj_set_role: string | null
          dj_tags_json: Json | null
          dj_updated_at: string | null
          duration_s: number | null
          first_seen_at: string | null
          genre: string | null
          identity_created_at: string | null
          identity_enriched_at: string | null
          identity_id: number | null
          identity_key: string | null
          identity_status: string | null
          identity_updated_at: string | null
          integrity_checked_at: string | null
          integrity_state: string | null
          isrc: string | null
          last_seen_at: string | null
          merged_into_id: number | null
          mix_name: string | null
          musical_key: string | null
          preferred_asset_id: number | null
          sample_rate: number | null
          sha256: string | null
          sub_genre: string | null
          title: string | null
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["preferred_asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "track_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_active_identity"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_export_metadata_v1"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_orphan_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_active_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_pool_candidates_v3"
            referencedColumns: ["identity_id"]
          },
          {
            foreignKeyName: "track_identity_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_dj_ready_candidates"
            referencedColumns: ["identity_id"]
          },
        ]
      }
      v_dj_ready_candidates: {
        Row: {
          artist: string | null
          bpm: number | null
          dj_tags_json: Json | null
          duration_s: number | null
          energy: number | null
          genre: string | null
          identity_id: number | null
          identity_key: string | null
          key: string | null
          last_played_at: string | null
          notes: string | null
          preferred_asset_id: number | null
          preferred_path: string | null
          rating: number | null
          set_role: string | null
          status: string | null
          title: string | null
        }
        Relationships: [
          {
            foreignKeyName: "preferred_asset_asset_id_fkey"
            columns: ["preferred_asset_id"]
            isOneToOne: false
            referencedRelation: "asset_file"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const

