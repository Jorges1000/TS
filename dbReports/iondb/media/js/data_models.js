function addCommas(nStr) {
    nStr += '';
    var x = nStr.split('.');
    var x1 = x[0];
    var x2 = x.length > 1 ? '.' + x[1] : '';
    var rgx = /(\d+)(\d{3})/;
    while (rgx.test(x1)) {
        x1 = x1.replace(rgx, '$1' + ',' + '$2');
    }
    return x1 + x2;
}

function precisionUnits(num) {
    // console.log(num + ' ' + typeof(num));
    num = parseFloat(num);
    var postfix = "";
    var exponent = Math.floor(Math.log(num) / Math.log(1000));
    if (exponent >= 0) {
        num = Math.round(100 * num / Math.pow(1000, exponent)) / 100;
    }
    if (Math.round(num) >= 1000) {
        num /= 1000;
        exponent += 1;
    }
    if (exponent >= 1) {
        postfix = "kMGTPEY"[exponent - 1];
    }
    return num.toPrecision(3) + ' ' + postfix;
}

$(function(){
    // This proxies all usual API calling events to The Void.
    /*Backbone.sync = function(method, model, success, error){
        success();
    };*/

    // includes bindings for fetching/fetched

    PaginatedCollection = Backbone.Collection.extend({
        initialize: function(models, options) {
            _.bindAll(this, 'parse', 'url', 'pageInfo', 'nextPage', 'previousPage', 'filtrate', 'order_by');
            typeof(options) != 'undefined' || (options = {});
            typeof(options.limit) != 'undefined' && (this.limit = options.limit);
            typeof(this.limit) != 'undefined' || (this.limit = 20);
            typeof(this.offset) != 'undefined' || (this.offset = 0);
            typeof(this.filter_options) != 'undefined' || (this.filter_options = {});
            typeof(this.sort_field) != 'undefined' || (this.sort_field = '');
        },

        fetch: function(options) {
            console.log("Fetching");
            typeof(options) != 'undefined' || (options = {});
            //this.trigger("fetching");s
            var self = this;
            var success = options.success;
            options.success = function(resp) {
                //self.trigger("fetched");
                if(success) { success(self, resp); }
            };
            return Backbone.Collection.prototype.fetch.call(this, options);
        },

        parse: function(resp) {
            console.log("Parsing response");
            this.offset = resp.meta.offset;
            this.limit = resp.meta.limit;
            this.total = resp.meta.total_count;
            return resp.objects;
        },

        // Add a model, or list of models to the set. Pass **silent** to avoid
        // firing the `add` event for every new model.
        update: function(models, options) {
            var i, index, length, model, cid, id, cids = {}, ids = {}, dups = [];
            options || (options = {});
            models = _.isArray(models) ? models.slice() : [models];

            // Begin by turning bare objects into model references, and preventing
            // invalid models or duplicate models from being added.
            var new_length = 0;
            for (i = 0, length = models.length; i < length; i++) {
                if (!(model = models[i] = this._prepareModel(models[i], options))) {
                    throw new Error("Can't add an invalid model to a collection");
                }
                cid = model.cid;
                id = model.id;
                duplicate = cids[cid] || this._byCid[cid] || ((id != null) && (ids[id] || this._byId[id]));
                if (duplicate) {
                    dups.push(duplicate);
                } else {
                    dups.push(null);
                    new_length++;
                }
                cids[cid] = ids[id] = model;
            }

            // Listen to added models' events, and index models for lookup by
            // `id` and by `cid`.
            for (i = 0, length = models.length; i < length; i++) {
                if (!dups[i]) {
                    (model = models[i]).on('all', this._onModelEvent, this);
                    this._byCid[model.cid] = model;
                    if (model.id != null) this._byId[model.id] = model;
                }
            }

            // Removing missing models from the collection
            for (i = this.models.length - 1; i >= 0; i--) {
                model = this.models[i];
                id = model.id;
                if (!ids[id]) {
                    delete this._byId[model.id];
                    delete this._byCid[model.cid];
                    index = this.indexOf(model);
                    this.models.splice(index, 1);
                    this.length--;
                    if (!options.silent) {
                        options.index = index;
                        model.trigger('remove', model, this, options);
                    }
                    this._removeReference(model);
                }
            }

            // Insert models into the collection
            this.length += new_length;
            index = options.at != null ? options.at : this.models.length;
            for (i =0; i < length; i++) {
                model = models[i];
                if (dups[i] != null) {
                    dups[i].set(model, {silent: true});
                } else {
                    this.models.splice(index++, 0, model);
                }
            }

            //re-sorting if needed
            if (this.comparator) this.sort({silent: true});
            // Triggering `delete` and `add` events unless silenced.
            if (options.silent) return this;

            for (i = 0, length = this.models.length; i < length; i++) {
                model = this.models[i];
                options.index = i;
                if (dups[i]) {
                    model.change();
                } else {
                    console.log("Add");
                    console.log(model);
                    model.trigger('add', model, this, options);
                }
            }
            return this;
        },

        url: function() {
            urlparams = {offset: this.offset, limit: this.limit};
            urlparams = $.extend(urlparams, this.filter_options);
            if (this.sort_field) {
                urlparams = $.extend(urlparams, {order_by: this.sort_field});
            }
            var full_url = this.baseUrl + '/?' + $.param(urlparams);
            console.log(full_url);
            return full_url;
        },

        pageInfo: function() {
            var max = Math.min(this.total, this.offset + this.limit);
            
            if (this.total == this.pages * this.limit) {
                max = this.total;
            }
            
            var info = {
                total: this.total,
                offset: this.offset,
                limit: this.limit,
                pages: Math.ceil(this.total / this.limit),
                lower_range: this.offset + 1,
                upper_range: max,
                prev: false,
                next: false
            };

            if (this.offset > 0) {
                info.prev = (this.offset - this.limit) || 1;
            }

            if (this.offset + this.limit < info.total) {
                info.next = this.offset + this.limit;
            }

            return info;
        },

        nextPage: function() {
            if (!this.pageInfo().next) {
                return false;
            }
            this.offset = this.offset + this.limit;
            return this.fetch();
        },

        previousPage: function() {
            if (!this.pageInfo().prev) {
              return false;
            }
            this.offset = (this.offset - this.limit) || 0;
            return this.fetch();
        },

        lastPage: function () {
            if (!this.pageInfo().next) {
              return false;
            }
            this.offset = this.total - this.limit;
            return this.fetch();
        },

        firstPage: function () {
            if (!this.pageInfo().prev) {
                return false;
            }
            this.offset = 0;
            return this.fetch();
        },

        filtrate: function (options) {
            console.log("Filtering");
            this.filter_options = options || {};
            this.offset = 0;
            return this.fetch();
        },

        order_by: function (field) {
            this.sort_field = field;
            this.offset = 0;
            return this.fetch();
        }
    });
    
    PaginatedView = Backbone.View.extend({
        initialize: function() {
            _.bindAll(this, 'previous', 'next', 'render');
            this.collection.bind('reset', this.render);
            this.collection.bind('add', this.render);
            this.collection.bind('remove', this.render);
        },

        events: {
            'click .prev': 'previous',
            'click .next': 'next',
            'click .first': 'first',
            'click .last': 'last'
        },

        template: Hogan.compile($("#pagination_template").html()),

        render: function () {
            this.$el.html(this.template.render(this.collection.pageInfo()));
        },

        previous: function () {
            this.collection.previousPage();
            return false;
        },

        next: function () {
            this.collection.nextPage();
            return false;
        },

        first: function () {
            this.collection.firstPage();
            return false;
        },

        last: function () {
            this.collection.lastPage();
            return false;
        }
    });

    TastyModel = Backbone.Model.extend({
        url: function () {
            return this.baseUrl + "/" + this.id + "/"
        },

        patch: function (attributes) {
            this.set(attributes);
            $.ajax({
                url: this.url(),
                type: 'PATCH',
                data: JSON.stringify(attributes),
                contentType: 'application/json'
            });
        }
    });

    Report = TastyModel.extend({

        parse: function (response) {
            return _.extend(response, {
                timeStamp: new Date(Date._parse(response.timeStamp))
            });
        },

        isCompleted: function () {
            return this.get("status") == "Complete";
        },

        baseUrl: "/rundb/api/v1/results"
    });

    ReportList = PaginatedCollection.extend({
        model: Report,

        baseUrl: "/rundb/api/v1/compositeresult"
    });

    Run = TastyModel.extend({
        initialize: function () {
            this.reports = new ReportList(this.get('results'), {
                parse: true
            });
            var  run = this;
            this.bind('change', function(){
                run.reports.reset(run.get("results"));
            });
        },

        parse: function (response) {
            return _.extend(response, {
                date: new Date(Date._parse(response.date)),
                resultDate: new Date(Date._parse(response.resultDate))
            });
        },

        baseUrl: "/rundb/api/v1/experiment"
    });

    RunList = PaginatedCollection.extend({
        model: Run,

        baseUrl: "/rundb/api/v1/compositeexperiment"
    });

    RunRouter = Backbone.Router.extend({
        routes: {
            'full': 'full_view',
            'table': 'table_view'
        },

        full_view: function () {
            console.log("Full view!");
        },

        table_view: function () {
            console.log("Table view!");
        }
    });
    
});