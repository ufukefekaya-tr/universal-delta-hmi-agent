# Yerel proje alanı

`projects/<neutral-project-id>/` ignored müşteri çalışma alanıdır. Native input, özel PLC tags/adresleri, profile contract, reviews, human approval, outputs ve vendor/physical evidence burada kalır. Core'a gerçek makine adı veya private dosya kopyalanmaz.

[Yeni proje](../docs/NEW_PROJECT.md) ve [başlangıç promptu](../prompts/START_NEW_PROJECT.md) kullanılır. Kaynak immutable SHA ile korunur; output yeni/sürümlü `save_as` hedefidir. Hedef model/editor/format/resolution/driver her proje için kanıtlanır; qualification pilot modelleri başka projeye otomatik aktarılmaz.

Bu README public kalır; alt proje dosyalarını toplu `git add` ile ortak repo'ya dahil etme. Public neutral fixture `examples/` altında, hakları açık ve synthetic etiketiyle tutulur. Proje archive/retention yalnız exact scope ve kullanıcı yetkisiyle yapılır; private evidence'i silmeden önce görev acceptance/recovery ihtiyacını doğrula.
