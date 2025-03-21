# -*- coding: utf-8 -*-
import pytest
from django.contrib.admin.views.main import ChangeList
from mock import patch


@pytest.fixture
def changelist_factory(rf, admin_user):
    def factory(model_admin):
        """
        Build a changelist instance for the given admin for testing purposes.

        :param model_admin: The model admin to create the changelist for.
        :return: The changelist instance.
        :rtype: ChangeList
        """
        request = rf.get('/')
        request.user = admin_user
        method_name = 'get_queryset' if hasattr(ChangeList, 'get_queryset') else 'get_query_set'
        with patch('django.contrib.admin.views.main.ChangeList.{}'.format(method_name)):
            if hasattr(model_admin, 'get_changelist_instance'):
                return model_admin.get_changelist_instance(request)
            list_display = model_admin.get_list_display(request)
            return model_admin.get_changelist(request)(
                request, model_admin.model, list_display, model_admin.get_list_display_links(request, list_display),
                model_admin.list_filter, model_admin.date_hierarchy, model_admin.search_fields,
                model_admin.list_select_related, model_admin.list_per_page, model_admin.list_max_show_all,
                model_admin.list_editable, model_admin,
            )

    return factory
