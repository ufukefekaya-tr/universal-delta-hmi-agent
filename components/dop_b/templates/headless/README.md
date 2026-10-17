# Headless görev şablonları

Bu dosyalar yetki değildir. Güvenilen başlatıcı `task-policy.json` yer tutucularını mevcut host yolları, exact kaynak SHA'ları ve bağımsız ajan kimlikleriyle doldurur. Public repo hiçbir müşterinin/host'un yolunu içermez. Policy, state ve reviews native workspace/teslim dışında tutulur.

Job exact alanları: `schema_version: 1`, `profile_id`, `source_path` (workspace-relative), `design` (tam mevcut ortak IR). Hedef profili kendi kaynak kalibrasyonu belirler; job içinde policy/approval/command/installer alanları yoktur.

Review şablonundaki UNREVIEWED değeri PASS'a otomatik çevrilmez. Denetmen somut kanıtı ve bulgularını üretir; findings zinciri tetikleyici/kanıt/etki/düzeltme/tekrar-test taşır. Aesthetic_second önceki aesthetic_first raporunun ham SHA'sına, technical_native aesthetic_second ham SHA'sına bağlanır. Native subject, request dosyasındaki candidate_subject_sha256'dır.

Host orkestratörü görev başlangıcında reviewer erişimini/provenance'ını doğrular. MCP'nin tek başına bir LLM kimliği veya API anahtarı yoktur. Kullanıcıdan ikinci tasarım onayı istemeden aynı atanmış bağımsız ajanları çalıştır.
