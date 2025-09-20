
install_prefix =  
prefix = ${install_prefix}/usr
bindir = ${prefix}/bin
sysconfdir = ${install_prefix}/etc
systemddir = ${prefix}/lib/systemd/user
pipewireconfdir = ${sysconfdir}/pipewire


.PHONY: install
install:
	mkdir -p ${bindir} $(sysconfdir) $(systemddir) $(pipewireconfdir)/pipewire-pulse.conf.d $(pipewireconfdir)/pipewire.conf.d
	install -m 0755 feed_my_wled.py -t $(bindir)
	install -m 0644 feed_my_wled.conf.example -t $(sysconfdir)
	install -m 0644 feed-my-wled.service -t $(systemddir)
	install -m 0644 50-pipe.conf -t $(pipewireconfdir)/pipewire-pulse.conf.d
	install -m 0644 90-fft-output.conf.example -t $(pipewireconfdir)/pipewire.conf.d
	
