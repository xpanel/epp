package EPP::Config;

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2014 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use strict;
use warnings;

use vars qw(%c);

my $file = '/etc/registry/registry.conf';
open(CONFIG, $file) or die "can't open $file: $!";
	my @conf = <CONFIG>;
close CONFIG;

%c = map {
	s/#.*//;
	s/^\s+//;
	s/\s+$//;
	m/(.*?)\s*=\s*(.*)/;
} @conf;

1;


# End.