package EPP::EPPWriter;

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



use XML::Writer;
use EPP::Version;
use EPP::EPPResultCode;
use EPP::Date(date_epp);

use strict;
use warnings;

BEGIN {
	use Exporter ();
	our ($VERSION, @ISA, @EXPORT, @EXPORT_OK, %EXPORT_TAGS);

	$VERSION = do { my @r = (q$Revision: 1.01 $ =~ /\d+/g); sprintf "%d."."%02d" x $#r, @r};
	@ISA = qw(Exporter);
	@EXPORT = qw(epp_writer);
	@EXPORT_OK = qw();
	%EXPORT_TAGS = (all => \@EXPORT_OK);
}

my $command_handler_map = {
	'greeting'         => \&_greeting,
	'login'            => \&_common,
	'logout'           => \&_common,
	'check_contact'    => \&_check_contact,
	'info_contact'     => \&_info_contact,
	'transfer_contact' => \&_transfer_contact,
	'create_contact'   => \&_create_contact,
	'delete_contact'   => \&_common,
	'update_contact'   => \&_common,
	'check_domain'     => \&_check_domain,
	'create_domain'    => \&_create_domain,
	'delete_domain'    => \&_common,
	'info_domain'      => \&_info_domain,
	'renew_domain'     => \&_renew_domain,
	'transfer_domain'  => \&_transfer_domain,
	'update_domain'    => \&_common,
	'check_host'       => \&_check_host,
	'create_host'      => \&_create_host,
	'delete_host'      => \&_common,
	'info_host'        => \&_info_host,
	'info_balance'     => \&_info_balance,
	'update_host'      => \&_common,
	'poll'             => \&_poll,
	'unknown'          => \&_common
};

sub epp_writer {
	my ($resp) = @_;

	my $writer = new XML::Writer(OUTPUT => "self", DATA_MODE => 'true', DATA_INDENT => 4);
	$writer->xmlDecl('UTF-8', 'no');
	$writer->startTag('epp', 'xmlns' => 'urn:ietf:params:xml:ns:epp-1.0', 'xmlns:xsi' => 'http://www.w3.org/2001/XMLSchema-instance', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd');
	&{$command_handler_map->{$resp->{command}}}($writer, $resp);
	$writer->endTag(); # </epp>
	$writer->end();

	return ($writer->to_string());
}

sub _greeting {
	my ($writer, $resp) = @_;

	$writer->startTag('greeting');

		$writer->dataElement('svID', $resp->{svID});
		$writer->dataElement('svDate', date_epp());

		$writer->startTag('svcMenu');

			foreach my $ver (EPP_VERSIONS) {
				$writer->dataElement('version', $ver);
			}

			foreach my $lang (epp_languages()) {
				$writer->dataElement('lang', $lang);
			}

            foreach my $objuri (EPP_OBJURIS) {
                $writer->dataElement('objURI', $objuri);
            }

	        $writer->startTag('svcExtension');
	            foreach my $exturi (EPP_EXTENSIONS) {
		            $writer->dataElement('extURI', $exturi);
	            }
	        $writer->endTag(); # </svcExtension>

        $writer->endTag(); # </svcMenu>

        $writer->startTag('dcp');
			$writer->startTag('access');
				$writer->emptyTag('all');
			$writer->endTag(); # </access>
            $writer->startTag('statement');
                $writer->startTag('purpose');
                    $writer->emptyTag('admin');
                    $writer->emptyTag('prov');
                $writer->endTag(); # </purpose>
                $writer->startTag('recipient');
                    $writer->emptyTag('ours');
                    $writer->emptyTag('public');
                $writer->endTag(); # </recipient>
                $writer->startTag('retention');
                    $writer->emptyTag('stated');
                $writer->endTag(); # </retention>
            $writer->endTag(); # </statement>
        $writer->endTag(); # </dcp>
    $writer->endTag(); # </greeting>
}

sub _preamble {
    my ($writer, $resp) = @_;

    my $lang = 'en-US';
    if (defined($resp->{lang})) {
        $lang = $resp->{lang};
    }

    my $code = $resp->{resultCode};

    $writer->startTag('response');
        $writer->startTag('result', code => $code);
			my $msg = epp_result_totext($code, $lang);
			if ($resp->{human_readable_message}) {
				$msg = epp_result_totext($code, $lang) . ' : ' . $resp->{human_readable_message};
			}
            $writer->dataElement('msg', $msg);
			if ($resp->{optionalValue}) {
				$writer->startTag('value', $resp->{xmlns_obj} => $resp->{xmlns_obj_value});
					$writer->dataElement($resp->{obj_elem}, $resp->{obj_elem_value});
				$writer->endTag(); # </value>
			}
        $writer->endTag(); # </result>
}

sub _postamble {
    my ($writer, $resp) = @_;

    if (defined($resp->{clTRID}) || defined($resp->{svTRID})) {
        $writer->startTag('trID');
            $writer->dataElement('clTRID', $resp->{clTRID});
            $writer->dataElement('svTRID', $resp->{svTRID});
        $writer->endTag(); # </trID>
    }
    $writer->endTag(); # </response>
}


sub _common {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);
    _postamble($writer, $resp);
}

sub _poll {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

	if ($resp->{resultCode} == 1000) {
		$writer->startTag('msgQ', 'count' => $resp->{count}, 'id' => $resp->{id});
		$writer->endTag(); # </msgQ>
	}
	elsif ($resp->{resultCode} == 1301) {
		$writer->startTag('msgQ', 'count' => $resp->{count}, 'id' => $resp->{id});
		$writer->dataElement('qDate', $resp->{qDate});
		$writer->dataElement('msg', $resp->{msg}, 'lang' => $resp->{lang});
		$writer->endTag(); # </msgQ>
		#---------------- <resData>
		if ($resp->{poll_msg_type} eq 'lowBalance') {
			$writer->startTag('resData');
				$writer->startTag('lowbalance-poll:pollData', 'xmlns:lowbalance-poll' => 'http://www.nic.xx/XXNIC-EPP/lowbalance-poll-1.0', 'xsi:schemaLocation' => 'http://www.nic.xx/XXNIC-EPP/lowbalance-poll-1.0 lowbalance-poll-1.0.xsd');
				$writer->dataElement('lowbalance-poll:registrarName', $resp->{registrarName});
				$writer->dataElement('lowbalance-poll:creditLimit', $resp->{creditLimit});
				$writer->dataElement('lowbalance-poll:creditThreshold', $resp->{creditThreshold}, 'type' => $resp->{creditThresholdType});
				$writer->dataElement('lowbalance-poll:availableCredit', $resp->{availableCredit});
				$writer->endTag(); # </lowbalance-poll:pollData>
			$writer->endTag(); # </resData>
		}
		elsif ($resp->{poll_msg_type} eq 'domainTransfer') {
			$writer->startTag('resData');
				$writer->startTag('domain:trnData', 'xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0');
				$writer->dataElement('domain:name', $resp->{name});
				$writer->dataElement('domain:trStatus', $resp->{obj_trStatus});
				$writer->dataElement('domain:reID', $resp->{obj_reID});
				$writer->dataElement('domain:reDate', $resp->{obj_reDate});
				$writer->dataElement('domain:acID', $resp->{obj_acID});
				$writer->dataElement('domain:acDate', $resp->{obj_acDate});
				if ($resp->{obj_exDate}) {
				$writer->dataElement('domain:exDate', $resp->{obj_exDate});
				}
				$writer->endTag(); # </domain:trnData>
			$writer->endTag(); # </resData>
		}
		elsif ($resp->{poll_msg_type} eq 'contactTransfer') {
			$writer->startTag('resData');
				$writer->startTag('contact:trnData', 'xmlns:contact' => 'urn:ietf:params:xml:ns:contact-1.0');
				$writer->dataElement('contact:id', $resp->{identifier});
				$writer->dataElement('contact:trStatus', $resp->{obj_trStatus});
				$writer->dataElement('contact:reID', $resp->{obj_reID});
				$writer->dataElement('contact:reDate', $resp->{obj_reDate});
				$writer->dataElement('contact:acID', $resp->{obj_acID});
				$writer->dataElement('contact:acDate', $resp->{obj_acDate});
				$writer->endTag(); # </contact:trnData>
			$writer->endTag(); # </resData>
		}
		#---------------- </resData>
	}

	_postamble($writer, $resp);
}

sub _check_contact {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {

        $writer->startTag('resData');
            $writer->startTag('contact:chkData', 'xmlns:contact' => 'urn:ietf:params:xml:ns:contact-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:contact-1.0 contact-1.0.xsd');
                foreach my $ids (@{$resp->{ids}}) {
                    $writer->startTag('contact:cd');
                        $writer->dataElement('contact:id', @{$ids}[0], 'avail' => @{$ids}[1]);
                        if (defined(@{$ids}[2])) {
                            $writer->dataElement('contact:reason', @{$ids}[2]);
                        }
                    $writer->endTag(); # </contact:cd>
                }
            $writer->endTag(); # </contact:chkData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _info_contact {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {

        $writer->startTag('resData');
            $writer->startTag('contact:infData', 'xmlns:contact' => 'urn:ietf:params:xml:ns:contact-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:contact-1.0 contact-1.0.xsd');
                $writer->dataElement('contact:id', $resp->{id});
                $writer->dataElement('contact:roid', $resp->{roid});

                if (scalar(@{$resp->{status}})) {
                    foreach my $s (@{$resp->{status}}) {
                        if (defined(@{$s}[1]) && defined(@{$s}[2])) {
                            $writer->dataElement('contact:status', @{$s}[2], 's' => ${$s}[0], 'lang' => ${$s}[1]);
                        }
						else {
                            $writer->emptyTag('contact:status', 's' => ${$s}[0]);
                        }
                    }
                }

                foreach my $t (keys %{$resp->{postal}}) {
                    $writer->startTag('contact:postalInfo', 'type' => $t);
                        $writer->dataElement('contact:name', $resp->{postal}->{$t}->{name});
                        $writer->dataElement('contact:org', $resp->{postal}->{$t}->{org});
                        $writer->startTag('contact:addr');
                            foreach my $s (@{$resp->{postal}->{$t}->{street}}) {
                                $writer->dataElement('contact:street', $s) if ($s);
                            }
                            $writer->dataElement('contact:city', $resp->{postal}->{$t}->{city});
                            if (defined($resp->{postal}->{$t}->{sp})) {
								$writer->dataElement('contact:sp', $resp->{postal}->{$t}->{sp});
							}
                            if (defined($resp->{postal}->{$t}->{pc})) {
                                $writer->dataElement('contact:pc', $resp->{postal}->{$t}->{pc});
							}
                            $writer->dataElement('contact:cc', $resp->{postal}->{$t}->{cc});
                        $writer->endTag(); # </contact:addr>
                    $writer->endTag(); # </contact:postalInfo>
                }
                if (defined($resp->{voice_x})) {
                    $writer->dataElement('contact:voice', $resp->{voice}, 'x' => $resp->{voice_x});
                }
				else {
                    $writer->dataElement('contact:voice', $resp->{voice});
                }
                if (defined($resp->{fax_x})) {
                    $writer->dataElement('contact:fax', $resp->{fax}, 'x' => $resp->{fax_x});
                }
				else {
                    $writer->dataElement('contact:fax', $resp->{fax});
                }
                $writer->dataElement('contact:email', $resp->{email});
                $writer->dataElement('contact:clID', $resp->{clID});
                $writer->dataElement('contact:crID', $resp->{crID});
                $writer->dataElement('contact:crDate', $resp->{crDate});
                if (defined($resp->{upID})) {
                    $writer->dataElement('contact:upID', $resp->{upID});
                }
                if (defined($resp->{upDate})) {
                    $writer->dataElement('contact:upDate', $resp->{upDate});
                }
                if (defined($resp->{trDate})) {
                    $writer->dataElement('contact:trDate', $resp->{trDate});
                }

				if ($resp->{authInfo} eq 'valid') {
					$writer->startTag('contact:authInfo');
					if ($resp->{authInfo_type} eq 'pw') {
						$writer->dataElement('contact:pw', $resp->{authInfo_val});
					}
					elsif ($resp->{authInfo_type} eq 'ext') {
						$writer->dataElement('contact:ext', $resp->{authInfo_val});
					}
					$writer->endTag(); # </contact:authInfo>
				}
            $writer->endTag(); # </contact:infData>
        $writer->endTag(); # </resData>
# -------------------
        $writer->startTag('extension');
            $writer->startTag('identExt:infData', 'xmlns:identExt' => 'http://www.nic.xx/XXNIC-EPP/identExt-1.0', 'xsi:schemaLocation' => 'http://www.nic.xx/XXNIC-EPP/identExt-1.0 identExt-1.0.xsd');
				$writer->dataElement('identExt:nin', $resp->{nin}, 'type' => $resp->{nin_type});
            $writer->endTag(); # </identExt:infData>
        $writer->endTag(); # </extension>
# -------------------
    }

	_postamble($writer, $resp);
}

sub _transfer_contact {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('contact:trnData', 'xmlns:contact' => 'urn:ietf:params:xml:ns:contact-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:contact-1.0 contact-1.0.xsd');
                $writer->dataElement('contact:id', $resp->{id});
                $writer->dataElement('contact:trStatus', $resp->{trStatus});
                $writer->dataElement('contact:reID', $resp->{reID});
                $writer->dataElement('contact:reDate', $resp->{reDate});
                $writer->dataElement('contact:acID', $resp->{acID});
                $writer->dataElement('contact:acDate', $resp->{acDate});
            $writer->endTag(); # </contact:trnData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _create_contact {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('contact:creData', 'xmlns:contact' => 'urn:ietf:params:xml:ns:contact-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:contact-1.0 contact-1.0.xsd');
                $writer->dataElement('contact:id', $resp->{id});
                $writer->dataElement('contact:crDate', $resp->{crDate});
            $writer->endTag(); # </contact:creData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _check_domain {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('domain:chkData', ('xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd'));
                foreach my $names (@{$resp->{names}}) {
                    $writer->startTag('domain:cd');
                        $writer->dataElement('domain:name', @{$names}[0], 'avail' => @{$names}[1]);
                        if (defined(@{$names}[2])) {
                            $writer->dataElement('domain:reason', @{$names}[2]);
                        }
                    $writer->endTag(); # </domain:cd>
                }
            $writer->endTag(); # </domain:chkData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _create_domain {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('domain:creData', 'xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd');
                $writer->dataElement('domain:name', $resp->{name});
                $writer->dataElement('domain:crDate', $resp->{crDate});
                $writer->dataElement('domain:exDate', $resp->{exDate});
            $writer->endTag(); # </domain:creData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _info_domain {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('domain:infData', 'xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd');
                $writer->dataElement('domain:name', $resp->{name});
                $writer->dataElement('domain:roid', $resp->{roid});

                if (defined($resp->{status}) && scalar(@{$resp->{status}})) {
                    foreach my $s (@{$resp->{status}}) {
                        if (defined(@{$s}[1]) && defined(@{$s}[2])) {
                            $writer->dataElement('domain:status', @{$s}[2], 's' => ${$s}[0], 'lang' => ${$s}[1]);
                        }
						else {
                            $writer->emptyTag('domain:status', 's' => ${$s}[0]);
                        }
                    }
                }

				if (defined($resp->{registrant})) {
					$writer->dataElement('domain:registrant', $resp->{registrant});
				}
                foreach my $t (@{$resp->{contact}}) {
					$writer->dataElement('domain:contact', @{$t}[1], 'type' => ${$t}[0]);
                }
				if ($resp->{return_ns}) {
					$writer->startTag('domain:ns');
						foreach my $n (@{$resp->{hostObj}}) {
							$writer->dataElement('domain:hostObj', $n);
						}
					$writer->endTag();
				}
				if ($resp->{return_host}) {
					foreach my $h (@{$resp->{host}}) {
						$writer->dataElement('domain:host', $h);
					}
				}
				$writer->dataElement('domain:clID', $resp->{clID});
		if (defined($resp->{crID})) {
                    $writer->dataElement('domain:crID', $resp->{crID});
		}
		if (defined($resp->{crDate})) {
                    $writer->dataElement('domain:crDate', $resp->{crDate});
		}
		if (defined($resp->{exDate})) {
                    $writer->dataElement('domain:exDate', $resp->{exDate});
		}
                if (defined($resp->{upID})) {
                    $writer->dataElement('domain:upID', $resp->{upID});
                }
                if (defined($resp->{upDate})) {
                    $writer->dataElement('domain:upDate', $resp->{upDate});
                }
                if (defined($resp->{trDate})) {
                    $writer->dataElement('domain:trDate', $resp->{trDate});
                }
				if ($resp->{authInfo} eq 'valid') {
					$writer->startTag('domain:authInfo');
					if ($resp->{authInfo_type} eq 'pw') {
						$writer->dataElement('domain:pw', $resp->{authInfo_val});
					}
					elsif ($resp->{authInfo_type} eq 'ext') {
						$writer->dataElement('domain:ext', $resp->{authInfo_val});
					}
					$writer->endTag(); # </domain:authInfo>
				}
            $writer->endTag(); # </domain:infData>
        $writer->endTag(); # </resData>
# -------------------
        $writer->startTag('extension');
            $writer->startTag('rgp:infData', 'xmlns:rgp' => 'urn:ietf:params:xml:ns:rgp-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:rgp-1.0 rgp-1.0.xsd');
				$writer->emptyTag('rgp:rgpStatus', 's' => $resp->{rgpstatus});
            $writer->endTag(); # </rgp:infData>
        $writer->endTag(); # </extension>
# -------------------
    }

    _postamble($writer, $resp);
}

sub _renew_domain {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('domain:renData', 'xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd');
                $writer->dataElement('domain:name', $resp->{name});
                $writer->dataElement('domain:exDate', $resp->{exDate});
            $writer->endTag(); # </domain:renData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _transfer_domain {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('domain:trnData', 'xmlns:domain' => 'urn:ietf:params:xml:ns:domain-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd');
                $writer->dataElement('domain:name', $resp->{name});
                $writer->dataElement('domain:trStatus', $resp->{trStatus});
                $writer->dataElement('domain:reID', $resp->{reID});
                $writer->dataElement('domain:reDate', $resp->{reDate});
                $writer->dataElement('domain:acID', $resp->{acID});
                $writer->dataElement('domain:acDate', $resp->{acDate});
				if (defined($resp->{exDate})) {
					$writer->dataElement('domain:exDate', $resp->{exDate});
				}
            $writer->endTag(); # </domain:trnData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _check_host {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('host:chkData', 'xmlns:host' => 'urn:ietf:params:xml:ns:host-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:host-1.0 host-1.0.xsd');

                foreach my $n (@{$resp->{names}}) {
                    $writer->startTag('host:cd');
                        $writer->dataElement('host:name', @{$n}[0], 'avail' => @{$n}[1]);
                        if (defined(@{$n}[2])) {
                            $writer->dataElement('host:reason', @{$n}[2]);
                        }
                    $writer->endTag(); # </host:cd>
                }
            $writer->endTag(); # </host:chkData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _create_host {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('host:creData', 'xmlns:host' => 'urn:ietf:params:xml:ns:host-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:host-1.0 host-1.0.xsd');
                $writer->dataElement('host:name', $resp->{name});
                $writer->dataElement('host:crDate', $resp->{crDate});
            $writer->endTag(); # </host:addData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _info_host {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('host:infData', 'xmlns:host' => 'urn:ietf:params:xml:ns:host-1.0', 'xsi:schemaLocation' => 'urn:ietf:params:xml:ns:host-1.0 host-1.0.xsd');
               $writer->dataElement('host:name', $resp->{name});
               $writer->dataElement('host:roid', $resp->{roid});

                if (scalar(@{$resp->{status}})) {
                    foreach my $s (@{$resp->{status}}) {
                        if (defined(@{$s}[1]) && defined(@{$s}[2])) {
                            $writer->dataElement('host:status', @{$s}[2], 's' => ${$s}[0], 'lang' => ${$s}[1]);
                        }
						else {
                            $writer->emptyTag('host:status', 's' => ${$s}[0]);
                        }
                    }
                }

                foreach my $a (@{$resp->{addr}}) {
                    $writer->dataElement('host:addr', @{$a}[1], 'ip' => 'v' . ${$a}[0]);
                }
                $writer->dataElement('host:clID', $resp->{clID});
                $writer->dataElement('host:crID', $resp->{crID});
                $writer->dataElement('host:crDate', $resp->{crDate});
                if (defined($resp->{upID})) {
                    $writer->dataElement('host:upID', $resp->{upID});
				}
                if (defined($resp->{upDate})) {
                    $writer->dataElement('host:upDate', $resp->{upDate});
				}
                if (defined($resp->{trDate})) {
                    $writer->dataElement('host:trDate', $resp->{trDate});
				}
           $writer->endTag(); # </host:infData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

sub _info_balance {
    my ($writer, $resp) = @_;

    _preamble($writer, $resp);

    if (epp_success($resp->{resultCode})) {
        $writer->startTag('resData');
            $writer->startTag('balance:infData', 'xmlns:balance' => 'http://www.nic.xx/XXNIC-EPP/balance-1.0', 'xsi:schemaLocation' => 'http://www.nic.xx/XXNIC-EPP/balance-1.0 balance-1.0.xsd');

               $writer->dataElement('balance:creditLimit', $resp->{creditLimit});
               $writer->dataElement('balance:balance', $resp->{balance});
               $writer->dataElement('balance:availableCredit', $resp->{availableCredit});
				$writer->startTag('balance:creditThreshold');
				if ($resp->{thresholdType} eq 'fixed') {
					$writer->dataElement('balance:fixed', $resp->{creditThreshold});
				}
				elsif ($resp->{thresholdType} eq 'percent') {
					$writer->dataElement('balance:percent', $resp->{creditThreshold});
				}
				$writer->endTag();

		   $writer->endTag(); # </balance:infData>
        $writer->endTag(); # </resData>
    }

    _postamble($writer, $resp);
}

1;