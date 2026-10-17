# Universal HMI Agents — giriş

Çalışma başlangıcında bu dosyayı, [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md) ve [INDEX.md](INDEX.md) dosyalarını tamamen oku. Üçü committed ve HEAD ile aynı olmalıdır. Kanonik politika SYSTEM_PROMPT.md içindedir.

Göreve uygun rol kartını ve yalnız ilgili belgeleri seç. Uzun/mutasyonlu görevde task envelope ve checkpoint kullan. Resume ve edit/commit öncesi `python tools/session_guard.py` ile epoch, kaynak ve kapsamı doğrula. Epoch: sabit sırada AGENTS.md, SYSTEM_PROMPT.md, INDEX.md için UTF-8 relative path + NUL + raw bytes + NUL akışının SHA-256 değeri.

Kaynaklara, vendor kurulumlarına veya başka projeye yazma. Tamamlanan mutasyon scoped yerel commit ile kapanır; push, IDE, PLC ve panel işlemleri bu yetkinin dışında kalır.
