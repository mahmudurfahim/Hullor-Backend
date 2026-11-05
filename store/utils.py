def file_url(file_field, fallback_url, request=None):
    """আপলোড করা ফাইলের URL (absolute), না থাকলে image_url ফিল্ড।"""
    if file_field:
        try:
            url = file_field.url
        except ValueError:
            url = ""
        if url:
            if request is not None and url.startswith("/"):
                return request.build_absolute_uri(url)
            return url
    return fallback_url or None


def product_image_urls(product, request=None):
    return [u for u in (file_url(i.image, i.url, request) for i in product.images.all()) if u]
