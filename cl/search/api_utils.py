from django.conf import settings

from cl.lib import search_utils
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import map_to_docket_entry_sorting


def get_object_list(request, cd, paginator):
    """Perform the Solr work"""
    # Set the offset value
    page_number = int(request.GET.get(paginator.page_query_param, 1))
    page_size = paginator.get_page_size(request)
    # Assume page_size = 20, then: 1 --> 0, 2 --> 20, 3 --> 40
    offset = max(0, (page_number - 1) * page_size)
    main_query = search_utils.build_main_query(cd, highlight='text',
                                               facet=False, group=False)
    main_query['caller'] = 'api_search'
    if cd['type'] == 'r':
        main_query['sort'] = map_to_docket_entry_sorting(main_query['sort'])
    sl = SolrList(main_query=main_query, offset=offset, type=cd['type'])
    return sl


class SolrList(object):
    """This implements a yielding list object that fetches items as they are
    queried.
    """

    def __init__(self, main_query, offset, type, length=None):
        super(SolrList, self).__init__()
        self.main_query = main_query
        self.offset = offset
        self.type = type
        self._item_cache = []
        if self.type == 'o':
            self.conn = ExtraSolrInterface(
                settings.SOLR_OPINION_URL,
                mode='r',
            )
        elif self.type == 'oa':
            self.conn = ExtraSolrInterface(
                settings.SOLR_AUDIO_URL,
                mode='r',
            )
        elif self.type == 'r':
            self.conn = ExtraSolrInterface(
                settings.SOLR_RECAP_URL,
                mode='r',
            )
        elif self.type == 'p':
            self.conn = ExtraSolrInterface(
                settings.SOLR_PEOPLE_URL,
                mode='r',
            )
        self._length = length

    def __len__(self):
        if self._length is None:
            mq = self.main_query.copy()  # local copy for manipulation
            mq['caller'] = 'api_search_count'
            count = self.conn.query().add_extra(**mq).count()
            self._length = count
        return self._length

    def __iter__(self):
        for item in range(0, len(self)):
            try:
                yield self._item_cache[item]
            except IndexError:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        self.main_query['start'] = self.offset
        r = self.conn.query().add_extra(**self.main_query).execute()

        if r.group_field is None:
            # Pull the text snippet up a level
            for result in r.result.docs:
                result['snippet'] = '&hellip;'.join(
                        result['solr_highlights']['text'])
                self._item_cache.append(SolrObject(initial=result))
        else:
            # Flatten group results, and pull up the text snippet as above.
            for group in getattr(r.groups, r.group_field)['groups']:
                for doc in group['doclist']['docs']:
                    doc['snippet'] = '&hellip;'.join(
                        doc['solr_highlights']['text'])
                    self._item_cache.append(SolrObject(initial=doc))

        # Now, assuming our _item_cache is all set, we just get the item.
        if isinstance(item, slice):
            s = slice(item.start - int(self.offset),
                      item.stop - int(self.offset),
                      item.step)
            return self._item_cache[s]
        else:
            # Not slicing.
            try:
                return self._item_cache[item]
            except IndexError:
                # No results!
                return []

    def append(self, p_object):
        """Lightly override the append method so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class SolrObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data
