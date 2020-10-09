import functools
import operator

from django.db.models import F
from django_filters import rest_framework as filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank, TrigramSimilarity
from gremlin_gplv3.users.models import User

class UserFilter(filters.FilterSet):
    text_search = filters.CharFilter(method='filter_search')
    #fuzzy_text_search = filters.CharFilter(method='fuzzy_search')
    role = filters.ChoiceFilter(choices=User.USER_ROLE)

    # This requires pg_trgm be installed in Postgres... which would be a pain in a half on docker and it's not clear
    # trigram matching would really give any better results.
    # def fuzzy_search(self, queryset, name, value):
    #     return queryset.annotate(similarity = TrigramSimilarity('name', value)).filter(similarity__gt=0.3)\
    #         .order_by('-similarity')

    def filter_search(self, queryset, name, value):
        #return queryset.annotate(search=SearchVector('name', 'username', 'email')).filter(search=value)

        # Thanks to https://www.mattlayman.com/blog/2017/postgres-search-django/
        # `search` is the user's provided search string.
        # terms = [SearchQuery(term) for term in value.split()]
        # vector = SearchVector('email', 'name', 'username')
        # query = functools.reduce(operator.or_, terms)
        # queryset = queryset.annotate(rank=SearchRank(vector, query)).order_by('-rank')
        # queryset = queryset.filter(rank__gte=0.04)

        # combined earlier approaches using this great guide: http://rubyjacket.com/build/django-psql-fts.html
        return queryset.annotate(rank=SearchRank(
            SearchVector('name', 'username', 'email'),
            SearchQuery(
                value,
                search_type="websearch",
                config="english"
            ))).order_by('-rank')

    class Meta:
        model = User
        fields = ['text_search', 'role'] #'fuzzy_text_search',

