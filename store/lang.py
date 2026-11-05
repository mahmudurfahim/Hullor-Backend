import re

_BN = re.compile(r"[\u0980-\u09FF]")


def has_bangla(text):
    return bool(_BN.search(text or ""))


def split_bn_en(text):
    """(bn, en): বাংলা অক্ষর থাকলে লেখাটা bn এ, নাহলে en এ। অন্যটা খালি।"""
    text = (text or "").strip()
    if not text:
        return "", ""
    return (text, "") if has_bangla(text) else ("", text)


def request_lang(request):
    """?lang=en হলে 'en', নাহলে 'bn'।"""
    if request is None:
        return "bn"
    params = getattr(request, "query_params", None)
    if params is None:
        params = getattr(request, "GET", {})
    return "en" if params.get("lang") == "en" else "bn"


class LangFieldsMixin:
    """lang_fields এর প্রতিটির জন্য <field>_en থাকলে এবং ?lang=en হলে সেটাই ফেরত দেয়।"""

    lang_fields = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if request_lang(self.context.get("request")) == "en":
            for f in self.lang_fields:
                val = (getattr(instance, f + "_en", "") or "").strip()
                if val:
                    data[f] = val
        return data
